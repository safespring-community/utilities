"""OpenStack connection handling."""

from dataclasses import dataclass
from typing import Any

import openstack
from openstack.connection import Connection

from migration.utils import ConnectionError, get_logger, retry


@dataclass
class CloudConnection:
    """Wrapper for OpenStack connection with metadata."""

    name: str
    connection: Connection
    verify_ssl: bool

    def __repr__(self) -> str:
        return f"CloudConnection(name={self.name!r}, verify_ssl={self.verify_ssl})"


@retry(max_attempts=3, backoff=2.0)
def connect(cloud_name: str, verify_ssl: bool = True) -> CloudConnection:
    """Connect to an OpenStack cloud using clouds.yaml configuration.

    Args:
        cloud_name: Name of the cloud in clouds.yaml.
        verify_ssl: Whether to verify SSL certificates.

    Returns:
        CloudConnection wrapper with the connection.

    Raises:
        ConnectionError: If connection fails.
    """
    logger = get_logger()
    logger.info(f"Connecting to cloud '{cloud_name}' (SSL verify: {verify_ssl})")

    try:
        conn = openstack.connect(cloud=cloud_name, verify=verify_ssl)
        # Test the connection by listing projects (lightweight API call)
        conn.identity.projects()
        logger.info(f"Successfully connected to '{cloud_name}'")
        return CloudConnection(name=cloud_name, connection=conn, verify_ssl=verify_ssl)
    except Exception as e:
        raise ConnectionError(f"Failed to connect to cloud '{cloud_name}': {e}") from e


def validate_connection(cloud: CloudConnection) -> bool:
    """Validate that a connection is still working.

    Args:
        cloud: Cloud connection to validate.

    Returns:
        True if connection is valid.

    Raises:
        ConnectionError: If connection is invalid.
    """
    logger = get_logger()
    logger.debug(f"Validating connection to '{cloud.name}'")

    try:
        # Simple API call to test connection
        cloud.connection.identity.projects()
        return True
    except Exception as e:
        raise ConnectionError(
            f"Connection to '{cloud.name}' is no longer valid: {e}"
        ) from e


def list_volumes(cloud: CloudConnection) -> list[dict[str, Any]]:
    """List all volumes in a cloud.

    Args:
        cloud: Cloud connection.

    Returns:
        List of volume dictionaries.
    """
    logger = get_logger()
    logger.debug(f"Listing volumes in '{cloud.name}'")

    volumes = []
    for vol in cloud.connection.block_storage.volumes():
        volumes.append(
            {
                "id": vol.id,
                "name": vol.name,
                "size": vol.size,
                "status": vol.status,
                "volume_type": vol.volume_type,
                "description": vol.description,
            }
        )

    logger.info(f"Found {len(volumes)} volumes in '{cloud.name}'")
    return volumes


def list_images(cloud: CloudConnection) -> list[dict[str, Any]]:
    """List all images in a cloud.

    Args:
        cloud: Cloud connection.

    Returns:
        List of image dictionaries.
    """
    logger = get_logger()
    logger.debug(f"Listing images in '{cloud.name}'")

    images = []
    for img in cloud.connection.image.images():
        images.append(
            {
                "id": img.id,
                "name": img.name,
                "status": img.status,
                "size": img.size,
                "min_disk": img.min_disk,
                "disk_format": img.disk_format,
                "visibility": img.visibility,
            }
        )

    logger.info(f"Found {len(images)} images in '{cloud.name}'")
    return images


def get_volume(cloud: CloudConnection, name_or_id: str) -> dict[str, Any] | None:
    """Get a specific volume by name or ID.

    Args:
        cloud: Cloud connection.
        name_or_id: Volume name or ID.

    Returns:
        Volume dictionary or None if not found.
    """
    logger = get_logger()
    logger.debug(f"Getting volume '{name_or_id}' from '{cloud.name}'")

    vol = cloud.connection.block_storage.find_volume(name_or_id)
    if vol is None:
        logger.warning(f"Volume '{name_or_id}' not found in '{cloud.name}'")
        return None

    return {
        "id": vol.id,
        "name": vol.name,
        "size": vol.size,
        "status": vol.status,
        "volume_type": vol.volume_type,
        "description": vol.description,
    }


def get_image(cloud: CloudConnection, name_or_id: str) -> dict[str, Any] | None:
    """Get a specific image by name or ID.

    Args:
        cloud: Cloud connection.
        name_or_id: Image name or ID.

    Returns:
        Image dictionary or None if not found.
    """
    logger = get_logger()
    logger.debug(f"Getting image '{name_or_id}' from '{cloud.name}'")

    img = cloud.connection.image.find_image(name_or_id)
    if img is None:
        logger.warning(f"Image '{name_or_id}' not found in '{cloud.name}'")
        return None

    return {
        "id": img.id,
        "name": img.name,
        "status": img.status,
        "size": img.size,
        "min_disk": img.min_disk,
        "disk_format": img.disk_format,
        "visibility": img.visibility,
    }
