"""Utility functions for logging, progress tracking, and common helpers."""

import logging
import shutil
import signal
import sys
from contextlib import contextmanager
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path
from time import sleep
from typing import Any, Callable, Generator, TypeVar

from rich.console import Console
from rich.logging import RichHandler
from rich.progress import (
    BarColumn,
    DownloadColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeRemainingColumn,
    TransferSpeedColumn,
)
from rich.prompt import Confirm

# Global console for rich output
console = Console()

# Type variable for generic retry decorator
T = TypeVar("T")


class MigrationError(Exception):
    """Base exception for migration errors."""

    pass


class ConnectionError(MigrationError):
    """Failed to connect to OpenStack cloud."""

    pass


class VolumeError(MigrationError):
    """Error during volume operations."""

    pass


class ImageError(MigrationError):
    """Error during image operations."""

    pass


class ConversionError(MigrationError):
    """Error during image format conversion."""

    pass


class DiskSpaceError(MigrationError):
    """Insufficient disk space for operation."""

    pass


class ResumeError(MigrationError):
    """Error resuming from saved state."""

    pass


def setup_logging(
    log_file: Path | None = None,
    verbose: int = 0,
) -> logging.Logger:
    """Configure logging with rich console and optional file output.

    Args:
        log_file: Optional path to write logs to.
        verbose: Verbosity level (0=WARNING, 1=INFO, 2=DEBUG).

    Returns:
        Configured logger instance.
    """
    level = {0: logging.WARNING, 1: logging.INFO}.get(verbose, logging.DEBUG)

    # Create logger
    logger = logging.getLogger("migration")
    logger.setLevel(logging.DEBUG)  # Capture all, filter at handler level
    logger.handlers.clear()

    # Rich console handler
    console_handler = RichHandler(
        console=console,
        show_time=True,
        show_path=False,
        rich_tracebacks=True,
    )
    console_handler.setLevel(level)
    logger.addHandler(console_handler)

    # File handler if requested
    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(logging.DEBUG)
        file_formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)

    return logger


def get_logger() -> logging.Logger:
    """Get the migration logger instance."""
    return logging.getLogger("migration")


def timestamp() -> str:
    """Return current UTC timestamp in ISO format."""
    return datetime.now(timezone.utc).isoformat()


def check_disk_space(path: Path, required_bytes: int) -> bool:
    """Check if sufficient disk space is available.

    Args:
        path: Path to check (uses the filesystem containing this path).
        required_bytes: Minimum required space in bytes.

    Returns:
        True if sufficient space is available.

    Raises:
        DiskSpaceError: If insufficient space is available.
    """
    stat = shutil.disk_usage(path.parent if path.is_file() else path)
    available = stat.free

    if available < required_bytes:
        required_gb = required_bytes / (1024**3)
        available_gb = available / (1024**3)
        raise DiskSpaceError(
            f"Insufficient disk space: {available_gb:.2f} GB available, "
            f"{required_gb:.2f} GB required"
        )
    return True


def bytes_to_human(num_bytes: float) -> str:
    """Convert bytes to human-readable string."""
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(num_bytes) < 1024:
            return f"{num_bytes:.2f} {unit}"
        num_bytes /= 1024
    return f"{num_bytes:.2f} PB"


def retry(
    max_attempts: int = 3,
    backoff: float = 2.0,
    exceptions: tuple[type[Exception], ...] = (Exception,),
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """Retry decorator with exponential backoff.

    Args:
        max_attempts: Maximum number of attempts.
        backoff: Base for exponential backoff (seconds).
        exceptions: Tuple of exceptions to catch and retry on.

    Returns:
        Decorated function.
    """

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            logger = get_logger()
            last_exception: Exception | None = None

            for attempt in range(max_attempts):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt < max_attempts - 1:
                        wait_time = backoff**attempt
                        logger.warning(
                            f"{func.__name__} failed (attempt {attempt + 1}/{max_attempts}): {e}. "
                            f"Retrying in {wait_time:.1f}s..."
                        )
                        sleep(wait_time)
                    else:
                        logger.error(
                            f"{func.__name__} failed after {max_attempts} attempts: {e}"
                        )

            if last_exception:
                raise last_exception
            raise RuntimeError("Retry logic error")  # Should never reach here

        return wrapper

    return decorator


@contextmanager
def cleanup_on_interrupt(
    cleanup_func: Callable[[], None],
) -> Generator[None, None, None]:
    """Context manager to ensure cleanup runs on SIGINT/SIGTERM.

    Args:
        cleanup_func: Function to call for cleanup.

    Yields:
        None
    """
    interrupted = False

    def handler(sig: int, frame: Any) -> None:
        nonlocal interrupted
        if not interrupted:
            interrupted = True
            console.print("\n[yellow]Interrupted! Cleaning up...[/yellow]")
            cleanup_func()
        sys.exit(1)

    old_sigint = signal.signal(signal.SIGINT, handler)
    old_sigterm = signal.signal(signal.SIGTERM, handler)

    try:
        yield
    finally:
        signal.signal(signal.SIGINT, old_sigint)
        signal.signal(signal.SIGTERM, old_sigterm)


def create_progress() -> Progress:
    """Create a rich progress bar for downloads/uploads."""
    return Progress(
        SpinnerColumn(),
        TextColumn("[bold blue]{task.description}"),
        BarColumn(),
        DownloadColumn(),
        TransferSpeedColumn(),
        TimeRemainingColumn(),
        console=console,
    )


def create_spinner_progress() -> Progress:
    """Create a rich progress bar for status polling."""
    return Progress(
        SpinnerColumn(),
        TextColumn("[bold blue]{task.description}"),
        console=console,
    )


def confirm(message: str, default: bool = False) -> bool:
    """Ask for user confirmation.

    Args:
        message: Confirmation message to display.
        default: Default value if user just presses Enter.

    Returns:
        True if user confirmed, False otherwise.
    """
    return Confirm.ask(message, default=default, console=console)


def print_success(message: str) -> None:
    """Print a success message."""
    console.print(f"[bold green]{message}[/bold green]")


def print_error(message: str) -> None:
    """Print an error message."""
    console.print(f"[bold red]Error: {message}[/bold red]")


def print_warning(message: str) -> None:
    """Print a warning message."""
    console.print(f"[bold yellow]Warning: {message}[/bold yellow]")


def print_info(message: str) -> None:
    """Print an info message."""
    console.print(f"[blue]{message}[/blue]")
