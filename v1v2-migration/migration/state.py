"""Resume state management for interrupted migrations."""

import json
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from migration.utils import ResumeError, get_logger, timestamp


class MigrationStep(str, Enum):
    """Steps in the migration workflow."""

    INIT = "init"
    CREATE_IMAGE = "create_image"
    WAIT_IMAGE = "wait_image"
    DOWNLOAD = "download"
    CONVERT = "convert"
    UPLOAD = "upload"
    CREATE_VOLUME = "create_volume"
    WAIT_VOLUME = "wait_volume"
    CLEANUP = "cleanup"
    COMPLETE = "complete"


@dataclass
class MigrationState:
    """State of an in-progress migration."""

    operation: str  # "volume" or "snapshot"
    source_cloud: str
    dest_cloud: str
    items_to_migrate: list[str] = field(default_factory=list)
    current_item: str = ""
    step: MigrationStep = MigrationStep.INIT
    temp_files: list[str] = field(default_factory=list)
    completed_items: list[str] = field(default_factory=list)
    failed_items: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = ""
    updated_at: str = ""

    def __post_init__(self) -> None:
        if not self.created_at:
            self.created_at = timestamp()
        self.updated_at = timestamp()


DEFAULT_STATE_FILE = Path(".migration_state.json")


def save_state(state: MigrationState, state_file: Path = DEFAULT_STATE_FILE) -> None:
    """Save migration state to file.

    Args:
        state: State to save.
        state_file: Path to state file.
    """
    logger = get_logger()
    state.updated_at = timestamp()

    data = asdict(state)
    # Convert enum to string for JSON serialization
    data["step"] = state.step.value

    try:
        with open(state_file, "w") as f:
            json.dump(data, f, indent=2)
        logger.debug(f"Saved state to {state_file}")
    except OSError as e:
        logger.warning(f"Failed to save state: {e}")


def load_state(state_file: Path = DEFAULT_STATE_FILE) -> MigrationState | None:
    """Load migration state from file.

    Args:
        state_file: Path to state file.

    Returns:
        Loaded state or None if file doesn't exist.

    Raises:
        ResumeError: If state file is corrupted.
    """
    logger = get_logger()

    if not state_file.exists():
        logger.debug(f"No state file found at {state_file}")
        return None

    try:
        with open(state_file) as f:
            data = json.load(f)

        # Convert step string back to enum
        data["step"] = MigrationStep(data["step"])

        state = MigrationState(**data)
        logger.info(f"Loaded state from {state_file}")
        logger.info(
            f"  Operation: {state.operation}, "
            f"Current item: {state.current_item}, "
            f"Step: {state.step.value}"
        )
        return state
    except json.JSONDecodeError as e:
        raise ResumeError(f"State file is corrupted: {e}") from e
    except (KeyError, ValueError) as e:
        raise ResumeError(f"State file has invalid format: {e}") from e


def clear_state(state_file: Path = DEFAULT_STATE_FILE) -> None:
    """Delete the state file.

    Args:
        state_file: Path to state file.
    """
    logger = get_logger()

    if state_file.exists():
        state_file.unlink()
        logger.debug(f"Cleared state file {state_file}")


def update_step(
    state: MigrationState,
    step: MigrationStep,
    state_file: Path = DEFAULT_STATE_FILE,
) -> None:
    """Update the current step and save state.

    Args:
        state: State to update.
        step: New step.
        state_file: Path to state file.
    """
    state.step = step
    save_state(state, state_file)


def add_temp_file(
    state: MigrationState,
    file_path: Path,
    state_file: Path = DEFAULT_STATE_FILE,
) -> None:
    """Add a temporary file to track for cleanup.

    Args:
        state: State to update.
        file_path: Path to temp file.
        state_file: Path to state file.
    """
    state.temp_files.append(str(file_path))
    save_state(state, state_file)


def mark_item_complete(
    state: MigrationState,
    item: str,
    state_file: Path = DEFAULT_STATE_FILE,
) -> None:
    """Mark an item as successfully migrated.

    Args:
        state: State to update.
        item: Item name that completed.
        state_file: Path to state file.
    """
    if item not in state.completed_items:
        state.completed_items.append(item)
    state.temp_files.clear()
    state.current_item = ""
    state.step = MigrationStep.INIT
    save_state(state, state_file)


def mark_item_failed(
    state: MigrationState,
    item: str,
    state_file: Path = DEFAULT_STATE_FILE,
) -> None:
    """Mark an item as failed.

    Args:
        state: State to update.
        item: Item name that failed.
        state_file: Path to state file.
    """
    if item not in state.failed_items:
        state.failed_items.append(item)
    save_state(state, state_file)


def cleanup_temp_files(state: MigrationState) -> None:
    """Clean up temporary files tracked in state.

    Args:
        state: State containing temp file paths.
    """
    logger = get_logger()

    for file_path_str in state.temp_files:
        file_path = Path(file_path_str)
        if file_path.exists():
            try:
                file_path.unlink()
                logger.debug(f"Cleaned up temp file: {file_path}")
            except OSError as e:
                logger.warning(f"Failed to clean up {file_path}: {e}")

    state.temp_files.clear()


def get_remaining_items(state: MigrationState) -> list[str]:
    """Get items that haven't been completed or failed yet.

    Args:
        state: Current state.

    Returns:
        List of remaining item names.
    """
    completed = set(state.completed_items)
    failed = set(state.failed_items)
    return [item for item in state.items_to_migrate if item not in completed | failed]


def can_resume_from_step(step: MigrationStep) -> bool:
    """Check if a migration can be resumed from a given step.

    Some steps can't be safely resumed (e.g., partial uploads).

    Args:
        step: Step to check.

    Returns:
        True if resumable.
    """
    # These steps have clear boundaries and can be resumed
    resumable = {
        MigrationStep.INIT,
        MigrationStep.DOWNLOAD,
        MigrationStep.CONVERT,
        MigrationStep.UPLOAD,
        MigrationStep.CREATE_VOLUME,
        MigrationStep.CLEANUP,
    }
    return step in resumable
