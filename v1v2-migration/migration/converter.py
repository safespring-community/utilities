"""qemu-img wrapper with progress tracking."""

import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, Callable

from migration.utils import ConversionError, create_progress, get_logger


def check_qemu_img() -> str:
    """Check if qemu-img is available.

    Returns:
        Path to qemu-img executable.

    Raises:
        ConversionError: If qemu-img is not found.
    """
    qemu_path = shutil.which("qemu-img")
    if qemu_path is None:
        raise ConversionError(
            "qemu-img not found. Please install qemu-utils:\n"
            "  Ubuntu/Debian: sudo apt install qemu-utils\n"
            "  macOS: brew install qemu\n"
            "  RHEL/CentOS: sudo yum install qemu-img"
        )
    return qemu_path


def _parse_progress(line: str) -> float | None:
    """Parse progress percentage from qemu-img output.

    Args:
        line: Output line from qemu-img.

    Returns:
        Progress percentage (0-100) or None if not a progress line.
    """
    # qemu-img outputs progress like: (12.34/100%)
    match = re.search(r"\((\d+(?:\.\d+)?)/100%\)", line)
    if match:
        return float(match.group(1))
    return None


def convert_raw_to_qcow2(
    input_path: Path,
    output_path: Path,
    show_progress: bool = True,
) -> Path:
    """Convert a raw image to qcow2 format.

    Args:
        input_path: Path to input raw image.
        output_path: Path for output qcow2 image.
        show_progress: Whether to show progress bar.

    Returns:
        Path to the converted image.

    Raises:
        ConversionError: If conversion fails.
    """
    logger = get_logger()
    qemu_path = check_qemu_img()

    if not input_path.exists():
        raise ConversionError(f"Input file does not exist: {input_path}")

    logger.info(f"Converting {input_path.name} to qcow2 format")

    # Build command with progress reporting
    cmd = [
        qemu_path,
        "convert",
        "-p",  # Progress reporting
        "-f",
        "raw",
        "-O",
        "qcow2",
        str(input_path),
        str(output_path),
    ]

    try:
        if show_progress:
            with create_progress() as progress:
                task = progress.add_task(
                    f"Converting {input_path.name}",
                    total=100,
                )

                # Run qemu-img with progress parsing
                proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                )

                # Read output and update progress
                last_progress = 0.0
                if proc.stdout is not None:
                    for line in proc.stdout:
                        parsed = _parse_progress(line)
                        if parsed is not None:
                            advance = parsed - last_progress
                            progress.update(task, advance=advance)
                            last_progress = parsed

                proc.wait()

                if proc.returncode != 0:
                    raise ConversionError(
                        f"qemu-img conversion failed with exit code {proc.returncode}"
                    )

                # Ensure we reach 100%
                if last_progress < 100:
                    progress.update(task, advance=100 - last_progress)
        else:
            # Run without progress display
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                raise ConversionError(f"qemu-img conversion failed: {result.stderr}")

        logger.info(f"Successfully converted to {output_path.name}")
        return output_path

    except subprocess.SubprocessError as e:
        raise ConversionError(f"Failed to run qemu-img: {e}") from e


def get_image_info(image_path: Path) -> dict[str, Any]:
    """Get information about an image file.

    Args:
        image_path: Path to the image file.

    Returns:
        Dictionary with image information.

    Raises:
        ConversionError: If info extraction fails.
    """
    qemu_path = check_qemu_img()

    if not image_path.exists():
        raise ConversionError(f"Image file does not exist: {image_path}")

    cmd = [qemu_path, "info", "--output=json", str(image_path)]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True,
        )
        return json.loads(result.stdout)
    except subprocess.CalledProcessError as e:
        raise ConversionError(f"Failed to get image info: {e.stderr}") from e
    except json.JSONDecodeError as e:
        raise ConversionError(f"Failed to parse image info: {e}") from e
