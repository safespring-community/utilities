"""Tests for snapshot migration module."""

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from migration.client import CloudConnection
from migration.snapshot import (
    display_images,
    download_image,
    migrate_single_snapshot,
    upload_image,
)
from migration.state import MigrationState
from migration.utils import ImageError


class TestDisplayImages:
    """Tests for display_images function."""

    def test_display_images(
        self, sample_images: list[dict[str, Any]], capsys: Any
    ) -> None:
        """Test image table display."""
        # Just ensure it doesn't raise
        display_images(sample_images, "test-cloud")


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

    def test_upload_failure(
        self, mock_openstack: MagicMock, sample_raw_file: Path
    ) -> None:
        """Test upload failure."""
        mock_openstack.image.create_image.side_effect = Exception("Upload failed")
        cloud = CloudConnection(
            name="test", connection=mock_openstack, verify_ssl=True
        )

        with pytest.raises(ImageError) as exc_info:
            upload_image(cloud, sample_raw_file, "new-image", min_disk=10)

        assert "Failed to upload" in str(exc_info.value)


class TestMigrateSingleSnapshot:
    """Tests for migrate_single_snapshot function."""

    def test_dry_run(self, mock_openstack: MagicMock, temp_dir: Path) -> None:
        """Test dry run mode."""
        source = CloudConnection(
            name="source", connection=mock_openstack, verify_ssl=True
        )
        dest = CloudConnection(
            name="dest", connection=mock_openstack, verify_ssl=True
        )
        state = MigrationState(
            operation="snapshot",
            source_cloud="source",
            dest_cloud="dest",
        )

        result = migrate_single_snapshot(
            source, dest, "test-image", state, dry_run=True, work_dir=temp_dir
        )

        assert result is True
        # No download should have occurred
        mock_openstack.image.download_image.assert_not_called()

    def test_image_not_found(self, mock_openstack: MagicMock, temp_dir: Path) -> None:
        """Test migration when image doesn't exist."""
        mock_openstack.image.find_image.return_value = None
        source = CloudConnection(
            name="source", connection=mock_openstack, verify_ssl=True
        )
        dest = CloudConnection(
            name="dest", connection=mock_openstack, verify_ssl=True
        )
        state = MigrationState(
            operation="snapshot",
            source_cloud="source",
            dest_cloud="dest",
        )

        result = migrate_single_snapshot(
            source, dest, "missing", state, dry_run=False, work_dir=temp_dir
        )

        assert result is False
