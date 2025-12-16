"""Snapshot/image migration workflow."""

from pathlib import Path
from typing import Any

from rich.prompt import Prompt
from rich.table import Table

from migration.client import CloudConnection, get_image, list_images
from migration.converter import convert_raw_to_qcow2
from migration.state import (
    MigrationState,
    MigrationStep,
    add_temp_file,
    cleanup_temp_files,
    mark_item_complete,
    mark_item_failed,
    save_state,
    update_step,
)
from migration.utils import (
    ImageError,
    bytes_to_human,
    check_disk_space,
    cleanup_on_interrupt,
    confirm,
    console,
    create_progress,
    get_logger,
    print_error,
    print_info,
    print_success,
    print_warning,
)


def display_images(images: list[dict[str, Any]], cloud_name: str) -> None:
    """Display images in a formatted table.

    Args:
        images: List of image dictionaries.
        cloud_name: Name of the cloud for display.
    """
    table = Table(title=f"Images in '{cloud_name}'")
    table.add_column("#", style="dim")
    table.add_column("Name", style="cyan")
    table.add_column("Size", justify="right")
    table.add_column("Status", style="green")
    table.add_column("Min Disk (GB)", justify="right")
    table.add_column("Format")

    for i, img in enumerate(images, 1):
        size_str = bytes_to_human(img["size"]) if img["size"] else "-"
        table.add_row(
            str(i),
            img["name"] or img["id"],
            size_str,
            img["status"],
            str(img["min_disk"]) if img["min_disk"] else "-",
            img["disk_format"] or "-",
        )

    console.print(table)


def select_images_interactive(
    cloud: CloudConnection,
) -> list[str]:
    """Interactively select images to migrate.

    Args:
        cloud: Source cloud connection.

    Returns:
        List of selected image names.
    """
    images = list_images(cloud)

    if not images:
        print_warning(f"No images found in '{cloud.name}'")
        return []

    display_images(images, cloud.name)

    print_info("\nEnter image numbers to migrate (comma-separated), or 'all' for all:")
    selection = Prompt.ask("Selection", console=console)

    if selection.lower() == "all":
        return [img["name"] or img["id"] for img in images]

    try:
        indices = [int(x.strip()) - 1 for x in selection.split(",")]
        selected = []
        for i in indices:
            if 0 <= i < len(images):
                selected.append(images[i]["name"] or images[i]["id"])
            else:
                print_warning(f"Invalid selection: {i + 1}")
        return selected
    except ValueError:
        print_error("Invalid input. Please enter numbers separated by commas.")
        return []


def download_image(
    cloud: CloudConnection,
    image_name: str,
    output_path: Path,
) -> Path:
    """Download an image to a local file.

    Args:
        cloud: Cloud connection.
        image_name: Name of the image.
        output_path: Path to save the image.

    Returns:
        Path to the downloaded file.

    Raises:
        ImageError: If download fails.
    """
    logger = get_logger()
    logger.info(f"Downloading image '{image_name}' to {output_path}")

    image = cloud.connection.image.find_image(image_name)
    if image is None:
        raise ImageError(f"Image '{image_name}' not found")

    # Check disk space (need at least 2x the image size for raw + qcow2)
    if image.size:
        check_disk_space(output_path.parent, image.size * 2)

    try:
        with create_progress() as progress:
            task = progress.add_task(
                f"Downloading {image_name}",
                total=image.size or 0,
            )

            with open(output_path, "wb") as f:
                response = cloud.connection.image.download_image(image, stream=True)
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        progress.update(task, advance=len(chunk))

        logger.info(f"Downloaded image to {output_path}")
        return output_path
    except Exception as e:
        # Clean up partial download
        if output_path.exists():
            output_path.unlink()
        raise ImageError(f"Failed to download image: {e}") from e


def upload_image(
    cloud: CloudConnection,
    image_path: Path,
    image_name: str,
    min_disk: int,
) -> dict[str, Any]:
    """Upload an image to a cloud.

    Args:
        cloud: Destination cloud connection.
        image_path: Path to the image file.
        image_name: Name for the uploaded image.
        min_disk: Minimum disk size in GB.

    Returns:
        Created image dictionary.

    Raises:
        ImageError: If upload fails.
    """
    logger = get_logger()
    logger.info(f"Uploading '{image_path.name}' as '{image_name}'")

    file_size = image_path.stat().st_size

    try:
        with create_progress() as progress:
            task = progress.add_task(f"Uploading {image_name}", total=file_size)

            # Create image with file upload
            with open(image_path, "rb") as f:
                image = cloud.connection.image.create_image(
                    name=image_name,
                    disk_format="qcow2",
                    container_format="bare",
                    visibility="private",
                    min_disk=min_disk,
                    data=f,
                )

            progress.update(task, completed=file_size)

        logger.info(f"Uploaded image '{image_name}' with ID {image.id}")
        return {
            "id": image.id,
            "name": image.name,
            "status": image.status,
        }
    except Exception as e:
        raise ImageError(f"Failed to upload image: {e}") from e


def migrate_single_snapshot(
    source: CloudConnection,
    dest: CloudConnection,
    image_name: str,
    state: MigrationState,
    dry_run: bool = False,
    work_dir: Path | None = None,
) -> bool:
    """Migrate a single image/snapshot from source to destination.

    Args:
        source: Source cloud connection.
        dest: Destination cloud connection.
        image_name: Name of the image to migrate.
        state: Migration state for tracking.
        dry_run: If True, only preview actions.
        work_dir: Working directory for temp files.

    Returns:
        True if successful, False otherwise.
    """
    logger = get_logger()
    work_dir = work_dir or Path.cwd()

    # Get image info
    img_info = get_image(source, image_name)
    if img_info is None:
        print_error(f"Image '{image_name}' not found in source cloud")
        return False

    size_str = bytes_to_human(img_info["size"]) if img_info["size"] else "unknown"
    min_disk = img_info["min_disk"] or 0

    print_info(f"\nMigrating image: {image_name}")
    print_info(f"  Size: {size_str}")
    print_info(f"  Min disk: {min_disk} GB")
    print_info(f"  Format: {img_info['disk_format'] or 'unknown'}")
    print_info(f"  Status: {img_info['status']}")

    if dry_run:
        print_info("\n[DRY RUN] Would perform the following steps:")
        print_info("  1. Download image to local disk")
        print_info("  2. Convert raw image to qcow2 format")
        print_info("  3. Upload qcow2 image to destination cloud")
        print_info("  4. Clean up temporary files")
        return True

    if img_info["status"] != "active":
        print_warning(
            f"Image status is '{img_info['status']}'. "
            "Migration may fail if image is not ready."
        )
        if not confirm("Continue anyway?"):
            return False

    # Update state
    state.current_item = image_name
    state.metadata = {
        "size": img_info["size"],
        "min_disk": min_disk,
    }
    save_state(state)

    raw_path = work_dir / f"{image_name}.raw"
    qcow2_path = work_dir / f"{image_name}.qcow2"

    def cleanup() -> None:
        """Clean up on interrupt or failure."""
        logger.info("Cleaning up...")
        cleanup_temp_files(state)
        if raw_path.exists():
            raw_path.unlink()
        if qcow2_path.exists():
            qcow2_path.unlink()

    with cleanup_on_interrupt(cleanup):
        try:
            # Step 1: Download
            update_step(state, MigrationStep.DOWNLOAD)
            add_temp_file(state, raw_path)
            print_info("\nStep 1/3: Downloading image...")
            download_image(source, image_name, raw_path)

            # Step 2: Convert
            update_step(state, MigrationStep.CONVERT)
            add_temp_file(state, qcow2_path)
            print_info("Step 2/3: Converting to qcow2...")
            convert_raw_to_qcow2(raw_path, qcow2_path)

            # Clean up raw file
            raw_path.unlink()
            state.temp_files.remove(str(raw_path))

            # Step 3: Upload
            update_step(state, MigrationStep.UPLOAD)
            print_info("Step 3/3: Uploading to destination...")
            upload_image(dest, qcow2_path, image_name, min_disk)

            # Clean up qcow2 file
            update_step(state, MigrationStep.CLEANUP)
            qcow2_path.unlink()
            state.temp_files.remove(str(qcow2_path))

            # Mark complete
            update_step(state, MigrationStep.COMPLETE)
            mark_item_complete(state, image_name)

            print_success(f"\nSuccessfully migrated image '{image_name}'!")
            return True

        except Exception as e:
            logger.exception(f"Failed to migrate image '{image_name}'")
            print_error(f"Migration failed: {e}")
            mark_item_failed(state, image_name)
            cleanup()
            return False
