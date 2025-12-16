"""Tests for volume migration module."""

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from migration.client import CloudConnection
from migration.state import MigrationState, MigrationStep
from migration.volume import (
    create_image_from_volume,
    create_volume_from_image,
    delete_image,
    display_volumes,
    download_image,
    migrate_single_volume,
    upload_image,
    wait_for_image_active,
    wait_for_volume_available,
)
from migration.utils import ImageError, VolumeError


class TestDisplayVolumes:
    """Tests for display_volumes function."""

    def test_display_volumes(
        self, sample_volumes: list[dict[str, Any]], capsys: Any
    ) -> None:
        """Test volume table display."""
        # Just ensure it doesn't raise
        display_volumes(sample_volumes, "test-cloud")


class TestCreateImageFromVolume:
    """Tests for create_image_from_volume function."""

    def test_create_image_success(self, mock_openstack: MagicMock) -> None:
        """Test successful image creation from volume."""
        cloud = CloudConnection(
            name="test", connection=mock_openstack, verify_ssl=True
        )

        result = create_image_from_volume(cloud, "test-volume")

        assert result == "test-volume.tmp"

    def test_create_image_volume_not_found(self, mock_openstack: MagicMock) -> None:
        """Test image creation when volume doesn't exist."""
        mock_openstack.block_storage.find_volume.return_value = None
        cloud = CloudConnection(
            name="test", connection=mock_openstack, verify_ssl=True
        )

        with pytest.raises(VolumeError) as exc_info:
            create_image_from_volume(cloud, "missing-volume")

        assert "not found" in str(exc_info.value)


class TestWaitForImageActive:
    """Tests for wait_for_image_active function."""

    def test_wait_success(self, mock_openstack: MagicMock) -> None:
        """Test waiting for image that becomes active."""
        cloud = CloudConnection(
            name="test", connection=mock_openstack, verify_ssl=True
        )

        result = wait_for_image_active(cloud, "test-image", timeout=10)

        assert result["status"] == "active"

    def test_wait_image_error(self, mock_openstack: MagicMock) -> None:
        """Test waiting for image that enters error state."""
        mock_image = MagicMock()
        mock_image.status = "error"
        mock_openstack.image.find_image.return_value = mock_image

        cloud = CloudConnection(
            name="test", connection=mock_openstack, verify_ssl=True
        )

        with pytest.raises(ImageError) as exc_info:
            wait_for_image_active(cloud, "test-image", timeout=10)

        assert "error state" in str(exc_info.value)


class TestDownloadImage:
    """Tests for download_image function."""

    def test_download_success(
        self, mock_openstack: MagicMock, temp_dir: Path
    ) -> None:
        """Test successful image download."""
        cloud = CloudConnection(
            name="test", connection=mock_openstack, verify_ssl=True
        )
        output_path = temp_dir / "downloaded.raw"

        result = download_image(cloud, "test-image", output_path)

        assert result == output_path
        assert output_path.exists()

    def test_download_image_not_found(
        self, mock_openstack: MagicMock, temp_dir: Path
    ) -> None:
        """Test download when image doesn't exist."""
        mock_openstack.image.find_image.return_value = None
        cloud = CloudConnection(
            name="test", connection=mock_openstack, verify_ssl=True
        )

        with pytest.raises(ImageError) as exc_info:
            download_image(cloud, "missing", temp_dir / "out.raw")

        assert "not found" in str(exc_info.value)


class TestUploadImage:
    """Tests for upload_image function."""

    def test_upload_success(
        self, mock_openstack: MagicMock, sample_raw_file: Path
    ) -> None:
        """Test successful image upload."""
        cloud = CloudConnection(
            name="test", connection=mock_openstack, verify_ssl=True
        )

        result = upload_image(cloud, sample_raw_file, "new-image", min_disk=10)

        assert result["name"] == "test-image"


class TestCreateVolumeFromImage:
    """Tests for create_volume_from_image function."""

    def test_create_volume_success(self, mock_openstack: MagicMock) -> None:
        """Test successful volume creation from image."""
        cloud = CloudConnection(
            name="test", connection=mock_openstack, verify_ssl=True
        )

        result = create_volume_from_image(
            cloud, "test-image", "new-volume", size=10, volume_type="fast"
        )

        assert result["name"] == "test-volume"

    def test_create_volume_image_not_found(self, mock_openstack: MagicMock) -> None:
        """Test volume creation when image doesn't exist."""
        mock_openstack.image.find_image.return_value = None
        cloud = CloudConnection(
            name="test", connection=mock_openstack, verify_ssl=True
        )

        with pytest.raises(VolumeError) as exc_info:
            create_volume_from_image(
                cloud, "missing-image", "vol", size=10, volume_type=None
            )

        assert "not found" in str(exc_info.value)


class TestWaitForVolumeAvailable:
    """Tests for wait_for_volume_available function."""

    def test_wait_success(self, mock_openstack: MagicMock) -> None:
        """Test waiting for volume that becomes available."""
        mock_volume = MagicMock()
        mock_volume.id = "vol-123"
        mock_volume.name = "test-volume"
        mock_volume.status = "available"
        mock_openstack.block_storage.find_volume.return_value = mock_volume

        cloud = CloudConnection(
            name="test", connection=mock_openstack, verify_ssl=True
        )

        result = wait_for_volume_available(cloud, "test-volume", timeout=10)

        assert result["status"] == "available"

    def test_wait_volume_error(self, mock_openstack: MagicMock) -> None:
        """Test waiting for volume that enters error state."""
        mock_volume = MagicMock()
        mock_volume.status = "error"
        mock_openstack.block_storage.find_volume.return_value = mock_volume

        cloud = CloudConnection(
            name="test", connection=mock_openstack, verify_ssl=True
        )

        with pytest.raises(VolumeError) as exc_info:
            wait_for_volume_available(cloud, "test-volume", timeout=10)

        assert "error state" in str(exc_info.value)


class TestDeleteImage:
    """Tests for delete_image function."""

    def test_delete_existing(self, mock_openstack: MagicMock) -> None:
        """Test deleting existing image."""
        cloud = CloudConnection(
            name="test", connection=mock_openstack, verify_ssl=True
        )

        # Should not raise
        delete_image(cloud, "test-image")

        mock_openstack.image.delete_image.assert_called_once()

    def test_delete_non_existing(self, mock_openstack: MagicMock) -> None:
        """Test deleting non-existing image (should not raise)."""
        mock_openstack.image.find_image.return_value = None
        cloud = CloudConnection(
            name="test", connection=mock_openstack, verify_ssl=True
        )

        # Should not raise
        delete_image(cloud, "missing")

        mock_openstack.image.delete_image.assert_not_called()


class TestMigrateSingleVolume:
    """Tests for migrate_single_volume function."""

    def test_dry_run(self, mock_openstack: MagicMock, temp_dir: Path) -> None:
        """Test dry run mode."""
        source = CloudConnection(
            name="source", connection=mock_openstack, verify_ssl=True
        )
        dest = CloudConnection(
            name="dest", connection=mock_openstack, verify_ssl=True
        )
        state = MigrationState(
            operation="volume",
            source_cloud="source",
            dest_cloud="dest",
        )

        result = migrate_single_volume(
            source, dest, "test-volume", state, dry_run=True, work_dir=temp_dir
        )

        assert result is True
        # No actual operations should have been performed
        mock_openstack.block_storage.upload_volume_to_image.assert_not_called()

    def test_volume_not_found(self, mock_openstack: MagicMock, temp_dir: Path) -> None:
        """Test migration when volume doesn't exist."""
        mock_openstack.block_storage.find_volume.return_value = None
        source = CloudConnection(
            name="source", connection=mock_openstack, verify_ssl=True
        )
        dest = CloudConnection(
            name="dest", connection=mock_openstack, verify_ssl=True
        )
        state = MigrationState(
            operation="volume",
            source_cloud="source",
            dest_cloud="dest",
        )

        result = migrate_single_volume(
            source, dest, "missing", state, dry_run=False, work_dir=temp_dir
        )

        assert result is False
