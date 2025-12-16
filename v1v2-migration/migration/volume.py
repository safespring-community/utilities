"""Volume migration workflow."""

from pathlib import Path
from time import sleep
from typing import Any

from rich.prompt import Prompt
from rich.table import Table

from migration.client import CloudConnection, get_volume, list_volumes
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
    VolumeError,
    bytes_to_human,
    check_disk_space,
    cleanup_on_interrupt,
    confirm,
    console,
    create_progress,
    create_spinner_progress,
    get_logger,
    print_error,
    print_info,
    print_success,
    print_warning,
    retry,
)


def display_volumes(volumes: list[dict[str, Any]], cloud_name: str) -> None:
    """Display volumes in a formatted table.

    Args:
        volumes: List of volume dictionaries.
        cloud_name: Name of the cloud for display.
    """
    table = Table(title=f"Volumes in '{cloud_name}'")
    table.add_column("#", style="dim")
    table.add_column("Name", style="cyan")
    table.add_column("Size (GB)", justify="right")
    table.add_column("Status", style="green")
    table.add_column("Type")

    for i, vol in enumerate(volumes, 1):
        table.add_row(
            str(i),
            vol["name"] or vol["id"],
            str(vol["size"]),
            vol["status"],
            vol["volume_type"] or "-",
        )

    console.print(table)


def select_volumes_interactive(
    cloud: CloudConnection,
) -> list[str]:
    """Interactively select volumes to migrate.

    Args:
        cloud: Source cloud connection.

    Returns:
        List of selected volume names.
    """
    volumes = list_volumes(cloud)

    if not volumes:
        print_warning(f"No volumes found in '{cloud.name}'")
        return []

    display_volumes(volumes, cloud.name)

    print_info("\nEnter volume numbers to migrate (comma-separated), or 'all' for all:")
    selection = Prompt.ask("Selection", console=console)

    if selection.lower() == "all":
        return [v["name"] or v["id"] for v in volumes]

    try:
        indices = [int(x.strip()) - 1 for x in selection.split(",")]
        selected = []
        for i in indices:
            if 0 <= i < len(volumes):
                selected.append(volumes[i]["name"] or volumes[i]["id"])
            else:
                print_warning(f"Invalid selection: {i + 1}")
        return selected
    except ValueError:
        print_error("Invalid input. Please enter numbers separated by commas.")
        return []


@retry(max_attempts=3, backoff=2.0)
def create_image_from_volume(
    cloud: CloudConnection,
    volume_name: str,
) -> str:
    """Create an image from a volume.

    Args:
        cloud: Cloud connection.
        volume_name: Name of the volume.

    Returns:
        Name of the created image.

    Raises:
        VolumeError: If image creation fails.
    """
    logger = get_logger()
    image_name = f"{volume_name}.tmp"

    logger.info(f"Creating image '{image_name}' from volume '{volume_name}'")

    try:
        volume = cloud.connection.block_storage.find_volume(volume_name)
        if volume is None:
            raise VolumeError(f"Volume '{volume_name}' not found")

        # Upload volume to image
        cloud.connection.block_storage.upload_volume_to_image(
            volume,
            image_name=image_name,
            disk_format="raw",
            container_format="bare",
        )

        return image_name
    except Exception as e:
        raise VolumeError(f"Failed to create image from volume: {e}") from e


def wait_for_image_active(
    cloud: CloudConnection,
    image_name: str,
    timeout: int = 3600,
) -> dict[str, Any]:
    """Wait for an image to become active.

    Args:
        cloud: Cloud connection.
        image_name: Name of the image.
        timeout: Maximum time to wait in seconds.

    Returns:
        Image dictionary.

    Raises:
        ImageError: If image fails or times out.
    """
    logger = get_logger()
    elapsed = 0
    poll_interval = 5

    with create_spinner_progress() as progress:
        task = progress.add_task(f"Waiting for image '{image_name}'...")

        while elapsed < timeout:
            image = cloud.connection.image.find_image(image_name)
            if image is None:
                raise ImageError(f"Image '{image_name}' not found")

            status = image.status
            progress.update(task, description=f"Image status: {status}")

            if status == "active":
                logger.info(f"Image '{image_name}' is active")
                return {
                    "id": image.id,
                    "name": image.name,
                    "status": status,
                    "size": image.size,
                    "min_disk": image.min_disk,
                }

            if status == "error":
                raise ImageError(f"Image '{image_name}' entered error state")

            sleep(poll_interval)
            elapsed += poll_interval

    raise ImageError(f"Timeout waiting for image '{image_name}' to become active")


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


def create_volume_from_image(
    cloud: CloudConnection,
    image_name: str,
    volume_name: str,
    size: int,
    volume_type: str | None,
) -> dict[str, Any]:
    """Create a volume from an image.

    Args:
        cloud: Cloud connection.
        image_name: Name of the source image.
        volume_name: Name for the new volume.
        size: Volume size in GB.
        volume_type: Volume type (optional).

    Returns:
        Created volume dictionary.

    Raises:
        VolumeError: If creation fails.
    """
    logger = get_logger()
    logger.info(f"Creating volume '{volume_name}' from image '{image_name}'")

    image = cloud.connection.image.find_image(image_name)
    if image is None:
        raise VolumeError(f"Image '{image_name}' not found")

    try:
        volume = cloud.connection.block_storage.create_volume(
            name=volume_name,
            size=size,
            image_id=image.id,
            volume_type=volume_type,
        )

        return {
            "id": volume.id,
            "name": volume.name,
            "status": volume.status,
        }
    except Exception as e:
        raise VolumeError(f"Failed to create volume: {e}") from e


def wait_for_volume_available(
    cloud: CloudConnection,
    volume_name: str,
    timeout: int = 3600,
) -> dict[str, Any]:
    """Wait for a volume to become available.

    Args:
        cloud: Cloud connection.
        volume_name: Name of the volume.
        timeout: Maximum time to wait in seconds.

    Returns:
        Volume dictionary.

    Raises:
        VolumeError: If volume fails or times out.
    """
    logger = get_logger()
    elapsed = 0
    poll_interval = 5

    with create_spinner_progress() as progress:
        task = progress.add_task(f"Waiting for volume '{volume_name}'...")

        while elapsed < timeout:
            volume = cloud.connection.block_storage.find_volume(volume_name)
            if volume is None:
                raise VolumeError(f"Volume '{volume_name}' not found")

            status = volume.status
            progress.update(task, description=f"Volume status: {status}")

            if status == "available":
                logger.info(f"Volume '{volume_name}' is available")
                return {
                    "id": volume.id,
                    "name": volume.name,
                    "status": status,
                }

            if status == "error":
                raise VolumeError(f"Volume '{volume_name}' entered error state")

            sleep(poll_interval)
            elapsed += poll_interval

    raise VolumeError(f"Timeout waiting for volume '{volume_name}' to become available")


def delete_image(cloud: CloudConnection, image_name: str) -> None:
    """Delete an image.

    Args:
        cloud: Cloud connection.
        image_name: Name of the image to delete.
    """
    logger = get_logger()
    image = cloud.connection.image.find_image(image_name)
    if image:
        cloud.connection.image.delete_image(image)
        logger.debug(f"Deleted image '{image_name}'")


def migrate_single_volume(
    source: CloudConnection,
    dest: CloudConnection,
    volume_name: str,
    state: MigrationState,
    dry_run: bool = False,
    work_dir: Path | None = None,
) -> bool:
    """Migrate a single volume from source to destination.

    Args:
        source: Source cloud connection.
        dest: Destination cloud connection.
        volume_name: Name of the volume to migrate.
        state: Migration state for tracking.
        dry_run: If True, only preview actions.
        work_dir: Working directory for temp files.

    Returns:
        True if successful, False otherwise.
    """
    logger = get_logger()
    work_dir = work_dir or Path.cwd()

    # Get volume info
    vol_info = get_volume(source, volume_name)
    if vol_info is None:
        print_error(f"Volume '{volume_name}' not found in source cloud")
        return False

    print_info(f"\nMigrating volume: {volume_name}")
    print_info(f"  Size: {vol_info['size']} GB")
    print_info(f"  Type: {vol_info['volume_type'] or 'default'}")
    print_info(f"  Status: {vol_info['status']}")

    if dry_run:
        print_info("\n[DRY RUN] Would perform the following steps:")
        print_info("  1. Create image from volume in source cloud")
        print_info("  2. Download image to local disk")
        print_info("  3. Convert raw image to qcow2 format")
        print_info("  4. Upload qcow2 image to destination cloud")
        print_info("  5. Create volume from image in destination cloud")
        print_info("  6. Clean up temporary files and images")
        return True

    if vol_info["status"] != "available":
        print_warning(
            f"Volume status is '{vol_info['status']}'. "
            "For safe migration, detach the volume first."
        )
        if not confirm("Continue anyway?"):
            return False

    # Update state
    state.current_item = volume_name
    state.metadata = {
        "size": vol_info["size"],
        "volume_type": vol_info["volume_type"],
    }
    save_state(state)

    raw_path = work_dir / f"{volume_name}.raw"
    qcow2_path = work_dir / f"{volume_name}.qcow2"
    temp_image_name = f"{volume_name}.tmp"
    dest_image_name = f"{volume_name}.img"

    def cleanup() -> None:
        """Clean up on interrupt or failure."""
        logger.info("Cleaning up...")
        cleanup_temp_files(state)
        if raw_path.exists():
            raw_path.unlink()
        if qcow2_path.exists():
            qcow2_path.unlink()
        delete_image(source, temp_image_name)
        delete_image(dest, dest_image_name)

    with cleanup_on_interrupt(cleanup):
        try:
            # Step 1: Create image from volume
            update_step(state, MigrationStep.CREATE_IMAGE)
            print_info("\nStep 1/6: Creating image from volume...")
            create_image_from_volume(source, volume_name)

            # Step 2: Wait for image
            update_step(state, MigrationStep.WAIT_IMAGE)
            print_info("Step 2/6: Waiting for image to be ready...")
            image_info = wait_for_image_active(source, temp_image_name)

            # Step 3: Download
            update_step(state, MigrationStep.DOWNLOAD)
            add_temp_file(state, raw_path)
            print_info("Step 3/6: Downloading image...")
            download_image(source, temp_image_name, raw_path)

            # Clean up source image
            delete_image(source, temp_image_name)

            # Step 4: Convert
            update_step(state, MigrationStep.CONVERT)
            add_temp_file(state, qcow2_path)
            print_info("Step 4/6: Converting to qcow2...")
            convert_raw_to_qcow2(raw_path, qcow2_path)

            # Clean up raw file
            raw_path.unlink()
            state.temp_files.remove(str(raw_path))

            # Step 5: Upload
            update_step(state, MigrationStep.UPLOAD)
            print_info("Step 5/6: Uploading to destination...")
            upload_image(dest, qcow2_path, dest_image_name, vol_info["size"])

            # Clean up qcow2 file
            qcow2_path.unlink()
            state.temp_files.remove(str(qcow2_path))

            # Step 6: Create volume
            update_step(state, MigrationStep.CREATE_VOLUME)
            print_info("Step 6/6: Creating volume in destination...")
            create_volume_from_image(
                dest,
                dest_image_name,
                volume_name,
                vol_info["size"],
                vol_info["volume_type"],
            )

            # Wait for volume
            update_step(state, MigrationStep.WAIT_VOLUME)
            wait_for_volume_available(dest, volume_name)

            # Cleanup destination image
            update_step(state, MigrationStep.CLEANUP)
            delete_image(dest, dest_image_name)

            # Mark complete
            update_step(state, MigrationStep.COMPLETE)
            mark_item_complete(state, volume_name)

            print_success(f"\nSuccessfully migrated volume '{volume_name}'!")
            return True

        except Exception as e:
            logger.exception(f"Failed to migrate volume '{volume_name}'")
            print_error(f"Migration failed: {e}")
            mark_item_failed(state, volume_name)
            cleanup()
            return False
