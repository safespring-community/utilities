"""Tests for qemu-img converter module."""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from migration.converter import (
    check_qemu_img,
    convert_raw_to_qcow2,
    get_image_info,
    _parse_progress,
)
from migration.utils import ConversionError


class TestCheckQemuImg:
    """Tests for check_qemu_img function."""

    def test_qemu_img_found(self, mocker: MagicMock) -> None:
        """Test when qemu-img is available."""
        mocker.patch("shutil.which", return_value="/usr/bin/qemu-img")

        result = check_qemu_img()

        assert result == "/usr/bin/qemu-img"

    def test_qemu_img_not_found(self, mocker: MagicMock) -> None:
        """Test when qemu-img is not installed."""
        mocker.patch("shutil.which", return_value=None)

        with pytest.raises(ConversionError) as exc_info:
            check_qemu_img()

        assert "qemu-img not found" in str(exc_info.value)


class TestParseProgress:
    """Tests for _parse_progress function."""

    def test_parse_valid_progress(self) -> None:
        """Test parsing valid progress output."""
        assert _parse_progress("(50.00/100%)") == 50.0
        assert _parse_progress("(0.00/100%)") == 0.0
        assert _parse_progress("(100.00/100%)") == 100.0
        assert _parse_progress("(33.33/100%)") == 33.33

    def test_parse_invalid_progress(self) -> None:
        """Test parsing non-progress output."""
        assert _parse_progress("some random text") is None
        assert _parse_progress("") is None
        assert _parse_progress("50%") is None


class TestConvertRawToQcow2:
    """Tests for convert_raw_to_qcow2 function."""

    def test_convert_success(
        self, temp_dir: Path, sample_raw_file: Path, mock_qemu_img: MagicMock
    ) -> None:
        """Test successful conversion."""
        output_path = temp_dir / "output.qcow2"

        result = convert_raw_to_qcow2(
            sample_raw_file, output_path, show_progress=False
        )

        assert result == output_path

    def test_convert_input_not_found(self, temp_dir: Path) -> None:
        """Test conversion with missing input file."""
        with pytest.raises(ConversionError) as exc_info:
            convert_raw_to_qcow2(
                temp_dir / "missing.raw",
                temp_dir / "output.qcow2",
            )

        assert "does not exist" in str(exc_info.value)

    def test_convert_failure(
        self, temp_dir: Path, sample_raw_file: Path, mocker: MagicMock
    ) -> None:
        """Test conversion failure."""
        mocker.patch("shutil.which", return_value="/usr/bin/qemu-img")
        mock_run = mocker.patch("subprocess.run")
        mock_run.return_value = MagicMock(returncode=1, stderr="Error")

        with pytest.raises(ConversionError):
            convert_raw_to_qcow2(
                sample_raw_file,
                temp_dir / "output.qcow2",
                show_progress=False,
            )


class TestGetImageInfo:
    """Tests for get_image_info function."""

    def test_get_info_success(
        self, temp_dir: Path, sample_raw_file: Path, mocker: MagicMock
    ) -> None:
        """Test getting image info."""
        mocker.patch("shutil.which", return_value="/usr/bin/qemu-img")
        mock_run = mocker.patch("subprocess.run")
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout='{"format": "raw", "virtual-size": 1024}',
        )

        info = get_image_info(sample_raw_file)

        assert info["format"] == "raw"
        assert info["virtual-size"] == 1024

    def test_get_info_file_not_found(self, temp_dir: Path) -> None:
        """Test getting info of missing file."""
        with pytest.raises(ConversionError) as exc_info:
            get_image_info(temp_dir / "missing.raw")

        assert "does not exist" in str(exc_info.value)
