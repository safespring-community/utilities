"""Pytest fixtures for migration tests."""

from pathlib import Path
from typing import Any, Generator
from unittest.mock import MagicMock, PropertyMock

import pytest


@pytest.fixture
def mock_openstack_connection(mocker: Any) -> MagicMock:
    """Create a mocked OpenStack connection."""
    mock_conn = MagicMock()

    # Mock identity service (for connection validation)
    mock_conn.identity.projects.return_value = [MagicMock(id="proj1", name="test")]

    # Mock block_storage service
    mock_volume = MagicMock()
    mock_volume.id = "vol-123"
    mock_volume.name = "test-volume"
    mock_volume.size = 10
    mock_volume.status = "available"
    mock_volume.volume_type = "fast"
    mock_volume.description = "Test volume"

    mock_conn.block_storage.volumes.return_value = [mock_volume]
    mock_conn.block_storage.find_volume.return_value = mock_volume
    mock_conn.block_storage.create_volume.return_value = mock_volume
    mock_conn.block_storage.upload_volume_to_image.return_value = None

    # Mock image service
    mock_image = MagicMock()
    mock_image.id = "img-123"
    mock_image.name = "test-image"
    mock_image.status = "active"
    mock_image.size = 1024 * 1024 * 1024  # 1 GB
    mock_image.min_disk = 10
    mock_image.disk_format = "raw"
    mock_image.visibility = "private"

    mock_conn.image.images.return_value = [mock_image]
    mock_conn.image.find_image.return_value = mock_image
    mock_conn.image.create_image.return_value = mock_image
    mock_conn.image.delete_image.return_value = None

    # Mock download with iterable response
    mock_response = MagicMock()
    mock_response.iter_content.return_value = [b"test data chunk"]
    mock_conn.image.download_image.return_value = mock_response

    return mock_conn


@pytest.fixture
def mock_openstack(mocker: Any, mock_openstack_connection: MagicMock) -> MagicMock:
    """Patch openstack.connect to return mocked connection."""
    mock_connect = mocker.patch("openstack.connect")
    mock_connect.return_value = mock_openstack_connection
    return mock_openstack_connection


@pytest.fixture
def temp_dir(tmp_path: Path) -> Path:
    """Create a temporary directory for tests."""
    return tmp_path


@pytest.fixture
def sample_raw_file(temp_dir: Path) -> Path:
    """Create a sample raw file for conversion tests."""
    raw_file = temp_dir / "test.raw"
    raw_file.write_bytes(b"\x00" * 1024)  # 1KB of zeros
    return raw_file


@pytest.fixture
def mock_qemu_img(mocker: Any) -> MagicMock:
    """Mock qemu-img command."""
    mock_which = mocker.patch("shutil.which")
    mock_which.return_value = "/usr/bin/qemu-img"

    mock_run = mocker.patch("subprocess.run")
    mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

    mock_popen = mocker.patch("subprocess.Popen")
    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_proc.stdout = iter(["(50.00/100%)\n", "(100.00/100%)\n"])
    mock_proc.wait.return_value = 0
    mock_popen.return_value = mock_proc

    return mock_run


@pytest.fixture
def mock_state_file(temp_dir: Path, mocker: Any) -> Path:
    """Create a temporary state file location."""
    state_file = temp_dir / ".migration_state.json"
    mocker.patch("migration.state.DEFAULT_STATE_FILE", state_file)
    return state_file


@pytest.fixture
def sample_volumes() -> list[dict[str, Any]]:
    """Sample volume data for tests."""
    return [
        {
            "id": "vol-1",
            "name": "volume-1",
            "size": 10,
            "status": "available",
            "volume_type": "fast",
            "description": "First volume",
        },
        {
            "id": "vol-2",
            "name": "volume-2",
            "size": 20,
            "status": "in-use",
            "volume_type": "slow",
            "description": "Second volume",
        },
    ]


@pytest.fixture
def sample_images() -> list[dict[str, Any]]:
    """Sample image data for tests."""
    return [
        {
            "id": "img-1",
            "name": "image-1",
            "status": "active",
            "size": 1024 * 1024 * 1024,
            "min_disk": 10,
            "disk_format": "raw",
            "visibility": "private",
        },
        {
            "id": "img-2",
            "name": "image-2",
            "status": "active",
            "size": 2 * 1024 * 1024 * 1024,
            "min_disk": 20,
            "disk_format": "qcow2",
            "visibility": "public",
        },
    ]
