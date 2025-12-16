"""Tests for OpenStack client module."""

from unittest.mock import MagicMock

import pytest

from migration.client import (
    CloudConnection,
    connect,
    get_image,
    get_volume,
    list_images,
    list_volumes,
    validate_connection,
)
from migration.utils import ConnectionError


class TestConnect:
    """Tests for connect function."""

    def test_connect_success(self, mock_openstack: MagicMock) -> None:
        """Test successful connection."""
        result = connect("test-cloud", verify_ssl=True)

        assert isinstance(result, CloudConnection)
        assert result.name == "test-cloud"
        assert result.verify_ssl is True

    def test_connect_with_insecure(self, mock_openstack: MagicMock) -> None:
        """Test connection with SSL verification disabled."""
        result = connect("test-cloud", verify_ssl=False)

        assert result.verify_ssl is False

    def test_connect_failure(self, mocker: MagicMock) -> None:
        """Test connection failure raises ConnectionError."""
        mock_connect = mocker.patch("openstack.connect")
        mock_connect.side_effect = Exception("Connection refused")

        with pytest.raises(ConnectionError) as exc_info:
            connect("bad-cloud")

        assert "Failed to connect" in str(exc_info.value)


class TestValidateConnection:
    """Tests for validate_connection function."""

    def test_validate_success(self, mock_openstack: MagicMock) -> None:
        """Test validation of working connection."""
        cloud = CloudConnection(
            name="test", connection=mock_openstack, verify_ssl=True
        )

        assert validate_connection(cloud) is True

    def test_validate_failure(self, mock_openstack: MagicMock) -> None:
        """Test validation of broken connection."""
        mock_openstack.identity.projects.side_effect = Exception("Unauthorized")
        cloud = CloudConnection(
            name="test", connection=mock_openstack, verify_ssl=True
        )

        with pytest.raises(ConnectionError):
            validate_connection(cloud)


class TestListVolumes:
    """Tests for list_volumes function."""

    def test_list_volumes(self, mock_openstack: MagicMock) -> None:
        """Test listing volumes."""
        cloud = CloudConnection(
            name="test", connection=mock_openstack, verify_ssl=True
        )

        volumes = list_volumes(cloud)

        assert len(volumes) == 1
        assert volumes[0]["name"] == "test-volume"
        assert volumes[0]["size"] == 10

    def test_list_volumes_empty(self, mock_openstack: MagicMock) -> None:
        """Test listing when no volumes exist."""
        mock_openstack.block_storage.volumes.return_value = []
        cloud = CloudConnection(
            name="test", connection=mock_openstack, verify_ssl=True
        )

        volumes = list_volumes(cloud)

        assert volumes == []


class TestListImages:
    """Tests for list_images function."""

    def test_list_images(self, mock_openstack: MagicMock) -> None:
        """Test listing images."""
        cloud = CloudConnection(
            name="test", connection=mock_openstack, verify_ssl=True
        )

        images = list_images(cloud)

        assert len(images) == 1
        assert images[0]["name"] == "test-image"
        assert images[0]["min_disk"] == 10


class TestGetVolume:
    """Tests for get_volume function."""

    def test_get_volume_found(self, mock_openstack: MagicMock) -> None:
        """Test getting existing volume."""
        cloud = CloudConnection(
            name="test", connection=mock_openstack, verify_ssl=True
        )

        volume = get_volume(cloud, "test-volume")

        assert volume is not None
        assert volume["name"] == "test-volume"

    def test_get_volume_not_found(self, mock_openstack: MagicMock) -> None:
        """Test getting non-existent volume."""
        mock_openstack.block_storage.find_volume.return_value = None
        cloud = CloudConnection(
            name="test", connection=mock_openstack, verify_ssl=True
        )

        volume = get_volume(cloud, "missing")

        assert volume is None


class TestGetImage:
    """Tests for get_image function."""

    def test_get_image_found(self, mock_openstack: MagicMock) -> None:
        """Test getting existing image."""
        cloud = CloudConnection(
            name="test", connection=mock_openstack, verify_ssl=True
        )

        image = get_image(cloud, "test-image")

        assert image is not None
        assert image["name"] == "test-image"

    def test_get_image_not_found(self, mock_openstack: MagicMock) -> None:
        """Test getting non-existent image."""
        mock_openstack.image.find_image.return_value = None
        cloud = CloudConnection(
            name="test", connection=mock_openstack, verify_ssl=True
        )

        image = get_image(cloud, "missing")

        assert image is None
