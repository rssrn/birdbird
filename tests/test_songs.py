"""Tests for songs.py parsing functions.

@author Claude Sonnet 4.5 Anthropic
"""

from datetime import datetime
from pathlib import Path

import pytest

from birdbird.songs import (
    SongDetection,
    parse_birdnet_csv,
    parse_dir_date,
    parse_timestamp_from_filename,
    validate_timestamps,
)


class TestParseDirDate:
    """Tests for parse_dir_date()."""

    def test_valid_date_directory(self, tmp_path):
        """Test with valid YYYYMMDD directory."""
        input_dir = tmp_path / "20260114"
        input_dir.mkdir()

        result = parse_dir_date(input_dir)

        assert result is not None
        assert result == datetime(2026, 1, 14)

    def test_invalid_format(self, tmp_path):
        """Test with invalid directory name format."""
        input_dir = tmp_path / "invalid"
        input_dir.mkdir()

        result = parse_dir_date(input_dir)

        assert result is None

    def test_wrong_length(self, tmp_path):
        """Test with wrong length directory name."""
        input_dir = tmp_path / "2026011"
        input_dir.mkdir()

        result = parse_dir_date(input_dir)

        assert result is None

    def test_non_numeric(self, tmp_path):
        """Test with non-numeric directory name."""
        input_dir = tmp_path / "202601ab"
        input_dir.mkdir()

        result = parse_dir_date(input_dir)

        assert result is None

    def test_invalid_date_values(self, tmp_path):
        """Test with invalid date values."""
        input_dir = tmp_path / "20261314"
        input_dir.mkdir()

        result = parse_dir_date(input_dir)

        assert result is None


class TestParseTimestampFromFilename:
    """Tests for parse_timestamp_from_filename()."""

    def test_valid_filename(self):
        """Test with valid filename format."""
        filename = "1408301500.avi"
        dir_date = datetime(2026, 1, 14)

        result = parse_timestamp_from_filename(filename, dir_date)

        assert result is not None
        assert result == "2026-01-14T08:30:15"

    def test_different_time(self):
        """Test parsing different time values."""
        filename = "1523594500.avi"
        dir_date = datetime(2026, 1, 15)

        result = parse_timestamp_from_filename(filename, dir_date)

        assert result == "2026-01-15T23:59:45"

    def test_midnight(self):
        """Test parsing midnight timestamp."""
        filename = "1400000000.avi"
        dir_date = datetime(2026, 1, 14)

        result = parse_timestamp_from_filename(filename, dir_date)

        assert result == "2026-01-14T00:00:00"

    def test_invalid_filename_format(self):
        """Test with invalid filename format."""
        filename = "invalid.avi"
        dir_date = datetime(2026, 1, 14)

        result = parse_timestamp_from_filename(filename, dir_date)

        assert result is None

    def test_missing_avi_extension(self):
        """Test with missing .avi extension."""
        filename = "1408301500.mp4"
        dir_date = datetime(2026, 1, 14)

        result = parse_timestamp_from_filename(filename, dir_date)

        assert result is None

    def test_too_short_filename(self):
        """Test with filename too short."""
        filename = "140830.avi"
        dir_date = datetime(2026, 1, 14)

        result = parse_timestamp_from_filename(filename, dir_date)

        assert result is None

    def test_none_dir_date(self):
        """Test with None dir_date."""
        filename = "1408301500.avi"

        result = parse_timestamp_from_filename(filename, None)

        assert result is None

    def test_invalid_time_values(self):
        """Test with invalid time values (e.g., hour 25)."""
        filename = "1425001500.avi"
        dir_date = datetime(2026, 1, 14)

        result = parse_timestamp_from_filename(filename, dir_date)

        # Should return None due to invalid hour
        assert result is None


class TestValidateTimestamps:
    """Tests for validate_timestamps()."""

    def test_valid_timestamps(self, tmp_path):
        """Test with valid timestamps."""
        input_dir = tmp_path / "20260114"
        input_dir.mkdir()

        # Clips from days 14, 15
        (input_dir / "1408301500.avi").touch()
        (input_dir / "1508301600.avi").touch()

        dir_date = datetime(2026, 1, 14)

        result = validate_timestamps(input_dir, dir_date)

        # Directory day (14) is within filename range (14-15)
        assert result is True

    def test_invalid_timestamps_out_of_range(self, tmp_path):
        """Test with timestamps out of range."""
        input_dir = tmp_path / "20260119"
        input_dir.mkdir()

        # Clips from days 01-03, but directory is day 19
        (input_dir / "0108301500.avi").touch()
        (input_dir / "0208301600.avi").touch()
        (input_dir / "0308301700.avi").touch()

        dir_date = datetime(2026, 1, 19)

        result = validate_timestamps(input_dir, dir_date)

        # Directory day (19) is NOT in filename range (01-03)
        assert result is False

    def test_month_boundary_valid(self, tmp_path):
        """Test with month boundary where timestamps are valid."""
        input_dir = tmp_path / "20260131"
        input_dir.mkdir()

        # Clips from days 30, 31, 01 (month boundary)
        (input_dir / "3008301500.avi").touch()
        (input_dir / "3108301600.avi").touch()
        (input_dir / "0108301700.avi").touch()

        dir_date = datetime(2026, 1, 31)

        result = validate_timestamps(input_dir, dir_date)

        # Directory day (31) is in range (30-31 or 01)
        assert result is True

    def test_none_dir_date(self, tmp_path):
        """Test with None dir_date."""
        input_dir = tmp_path / "20260114"
        input_dir.mkdir()
        (input_dir / "1408301500.avi").touch()

        result = validate_timestamps(input_dir, None)

        assert result is False

    def test_no_avi_files(self, tmp_path):
        """Test with no AVI files."""
        input_dir = tmp_path / "20260114"
        input_dir.mkdir()

        dir_date = datetime(2026, 1, 14)

        result = validate_timestamps(input_dir, dir_date)

        assert result is False

    def test_malformed_filenames(self, tmp_path):
        """Test with malformed filenames."""
        input_dir = tmp_path / "20260114"
        input_dir.mkdir()

        # Create files with malformed names
        (input_dir / "invalid.avi").touch()
        (input_dir / "abcdefgh00.avi").touch()

        dir_date = datetime(2026, 1, 14)

        result = validate_timestamps(input_dir, dir_date)

        assert result is False


class TestParseBirdnetCsv:
    """Tests for parse_birdnet_csv()."""

    def test_parse_valid_csv(self, sample_birdnet_csv):
        """Test parsing valid BirdNET CSV."""
        dir_date = datetime(2026, 1, 14)

        detections = parse_birdnet_csv(
            sample_birdnet_csv,
            "1408301500.avi",
            dir_date,
            timestamps_reliable=True,
        )

        assert len(detections) == 3

        # Check first detection
        assert detections[0].filename == "1408301500.avi"
        assert detections[0].common_name == "Eurasian Blue Tit"
        assert detections[0].scientific_name == "Cyanistes caeruleus"
        assert detections[0].confidence == 0.9134
        assert detections[0].start_s == 0.0
        assert detections[0].end_s == 3.0
        assert detections[0].timestamp == "2026-01-14T08:30:15"

        # Check second detection
        assert detections[1].common_name == "European Robin"
        assert detections[1].start_s == 5.0

    def test_parse_missing_csv(self, tmp_path):
        """Test parsing missing CSV file."""
        csv_path = tmp_path / "missing.csv"
        dir_date = datetime(2026, 1, 14)

        detections = parse_birdnet_csv(
            csv_path,
            "1408301500.avi",
            dir_date,
            timestamps_reliable=True,
        )

        assert detections == []

    def test_parse_unreliable_timestamps(self, sample_birdnet_csv):
        """Test parsing with unreliable timestamps."""
        dir_date = datetime(2026, 1, 14)

        detections = parse_birdnet_csv(
            sample_birdnet_csv,
            "1408301500.avi",
            dir_date,
            timestamps_reliable=False,
        )

        assert len(detections) == 3

        # Should use date only (no time)
        assert detections[0].timestamp == "2026-01-14"
        assert detections[1].timestamp == "2026-01-14"

    def test_parse_unreliable_timestamps_no_dir_date(self, sample_birdnet_csv):
        """Test parsing with unreliable timestamps and no dir_date."""
        detections = parse_birdnet_csv(
            sample_birdnet_csv,
            "1408301500.avi",
            None,
            timestamps_reliable=False,
        )

        assert len(detections) == 3

        # Should have empty timestamp
        assert detections[0].timestamp == ""

    def test_confidence_rounding(self, sample_birdnet_csv):
        """Test that confidence values are rounded."""
        dir_date = datetime(2026, 1, 14)

        detections = parse_birdnet_csv(
            sample_birdnet_csv,
            "1408301500.avi",
            dir_date,
            timestamps_reliable=True,
        )

        # Check that confidence is rounded to 4 decimal places
        for detection in detections:
            # Convert to dict to check the rounded value
            det_dict = detection.to_dict()
            assert isinstance(det_dict["confidence"], float)
            # Should be rounded to 4 decimals
            assert len(str(det_dict["confidence"]).split(".")[-1]) <= 4


class TestSongDetection:
    """Tests for SongDetection class."""

    def test_to_dict(self):
        """Test converting SongDetection to dict."""
        detection = SongDetection(
            filename="1408301500.avi",
            timestamp="2026-01-14T08:30:15",
            start_s=0.0,
            end_s=3.0,
            common_name="Eurasian Blue Tit",
            scientific_name="Cyanistes caeruleus",
            confidence=0.913456,
        )

        result = detection.to_dict()

        assert result["filename"] == "1408301500.avi"
        assert result["timestamp"] == "2026-01-14T08:30:15"
        assert result["start_s"] == 0.0
        assert result["end_s"] == 3.0
        assert result["common_name"] == "Eurasian Blue Tit"
        assert result["scientific_name"] == "Cyanistes caeruleus"
        # Confidence should be rounded to 4 decimals
        assert result["confidence"] == 0.9135
