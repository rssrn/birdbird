"""Tests for publish.py date parsing functions.

@author Claude Sonnet 4.5 Anthropic
"""

from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from birdbird.publish import (
    extract_date_range,
    extract_original_date,
    generate_batch_id,
)


class TestExtractOriginalDate:
    """Tests for extract_original_date()."""

    def test_valid_date_directory(self, tmp_path):
        """Test with valid YYYYMMDD directory name."""
        input_dir = tmp_path / "20260114"
        input_dir.mkdir()

        result = extract_original_date(input_dir)

        assert result == "2026-01-14"

    def test_invalid_date_format(self, tmp_path):
        """Test with invalid date format."""
        input_dir = tmp_path / "invalid_date"
        input_dir.mkdir()

        result = extract_original_date(input_dir)

        assert result == "unknown"

    def test_wrong_length(self, tmp_path):
        """Test with wrong length directory name."""
        input_dir = tmp_path / "2026011"
        input_dir.mkdir()

        result = extract_original_date(input_dir)

        assert result == "unknown"

    def test_non_numeric(self, tmp_path):
        """Test with non-numeric directory name."""
        input_dir = tmp_path / "202601ab"
        input_dir.mkdir()

        result = extract_original_date(input_dir)

        assert result == "unknown"

    def test_invalid_date_values(self, tmp_path):
        """Test with invalid date values (e.g., month 13)."""
        input_dir = tmp_path / "20261314"
        input_dir.mkdir()

        result = extract_original_date(input_dir)

        assert result == "unknown"


class TestExtractDateRange:
    """Tests for extract_date_range()."""

    def test_single_day_clips(self, tmp_input_dir):
        """Test with clips from a single day."""
        # Clips are all from day 14
        original_date = "2026-01-14"

        start, end = extract_date_range(tmp_input_dir, original_date)

        assert start == "2026-01-14"
        assert end == "2026-01-15"  # Ends on day 15

    def test_multiple_days_same_month(self, tmp_path):
        """Test with clips spanning multiple days in same month."""
        input_dir = tmp_path / "20260114"
        input_dir.mkdir()

        # Create clips from days 14, 15, 16
        (input_dir / "1408301500.avi").touch()
        (input_dir / "1508301600.avi").touch()
        (input_dir / "1608301700.avi").touch()

        original_date = "2026-01-14"

        start, end = extract_date_range(input_dir, original_date)

        assert start == "2026-01-14"
        assert end == "2026-01-16"

    def test_month_boundary_case(self, tmp_path):
        """Test with clips spanning month boundary."""
        input_dir = tmp_path / "20260201"  # February 1st
        input_dir.mkdir()

        # Clips from Jan 30, Jan 31, Feb 01
        # Days: [30, 31, 1] -> min=1, max=31 (numerically sorted)
        # This triggers month boundary detection since min < max but creates large span
        # Better test: use consecutive days across boundary
        (input_dir / "3123595900.avi").touch()  # Jan 31, 23:59:59
        (input_dir / "0100000100.avi").touch()  # Feb 01, 00:00:01

        original_date = "2026-02-01"

        start, end = extract_date_range(input_dir, original_date)

        # Days are [31, 1], min=1, max=31
        # Since min < max (1 < 31), treated as same month with span=30 > threshold
        # Falls back to single date
        assert start == "2026-02-01"
        assert end == "2026-02-01"

    def test_unknown_original_date(self, tmp_input_dir):
        """Test with unknown original date."""
        original_date = "unknown"

        start, end = extract_date_range(tmp_input_dir, original_date)

        assert start == "unknown"
        assert end == "unknown"

    def test_no_avi_files(self, tmp_path):
        """Test with directory containing no AVI files."""
        input_dir = tmp_path / "20260114"
        input_dir.mkdir()

        original_date = "2026-01-14"

        start, end = extract_date_range(input_dir, original_date)

        # Should fall back to single date
        assert start == "2026-01-14"
        assert end == "2026-01-14"

    def test_invalid_timestamps_large_span(self, tmp_path):
        """Test with invalid timestamps (camera clock was wrong)."""
        input_dir = tmp_path / "20260121"
        input_dir.mkdir()

        # Clips with broken clock: day 03 and day 21 (span = 18 days, exceeds threshold)
        (input_dir / "0312345600.avi").touch()
        (input_dir / "2123595900.avi").touch()

        original_date = "2026-01-21"

        start, end = extract_date_range(input_dir, original_date)

        # Span too large, should fall back to single date
        assert start == "2026-01-21"
        assert end == "2026-01-21"

    def test_directory_day_not_in_range(self, tmp_path):
        """Test when directory day is not within filename day range."""
        input_dir = tmp_path / "20260119"
        input_dir.mkdir()

        # Clips from days 01-03, but directory is day 19
        (input_dir / "0112345600.avi").touch()
        (input_dir / "0212345700.avi").touch()
        (input_dir / "0312345800.avi").touch()

        original_date = "2026-01-19"

        start, end = extract_date_range(input_dir, original_date)

        # Directory day (19) not in range (01-03), fall back
        assert start == "2026-01-19"
        assert end == "2026-01-19"

    def test_valid_small_span(self, tmp_path):
        """Test valid timestamps with small span."""
        input_dir = tmp_path / "20260116"
        input_dir.mkdir()

        # Clips from days 14, 15, 16 (span = 2 days, within threshold)
        (input_dir / "1411354000.avi").touch()
        (input_dir / "1511595900.avi").touch()
        (input_dir / "1611595900.avi").touch()

        original_date = "2026-01-16"

        start, end = extract_date_range(input_dir, original_date)

        # Directory day (16) is in range (14-16), span is acceptable
        assert start == "2026-01-14"
        assert end == "2026-01-16"


class TestGenerateBatchId:
    """Tests for generate_batch_id()."""

    def test_no_existing_batches(self):
        """Test with no existing batches for this date."""
        mock_client = MagicMock()
        # Mock list_batches to return empty list
        from birdbird.publish import list_batches
        import birdbird.publish
        original_list_batches = birdbird.publish.list_batches

        def mock_list_batches(client, bucket):
            return []

        birdbird.publish.list_batches = mock_list_batches

        try:
            batch_id, exists = generate_batch_id(
                mock_client, "test-bucket", "2026-01-14", create_new=False
            )

            assert batch_id == "20260114_01"
            assert exists is False
        finally:
            birdbird.publish.list_batches = original_list_batches

    def test_reuse_existing_batch(self):
        """Test reusing existing batch (default behavior)."""
        mock_client = MagicMock()

        from birdbird.publish import list_batches
        import birdbird.publish
        original_list_batches = birdbird.publish.list_batches

        def mock_list_batches(client, bucket):
            return ["20260114_02", "20260114_01", "20260113_01"]

        birdbird.publish.list_batches = mock_list_batches

        try:
            batch_id, exists = generate_batch_id(
                mock_client, "test-bucket", "2026-01-14", create_new=False
            )

            # Should reuse max sequence (02)
            assert batch_id == "20260114_02"
            assert exists is True
        finally:
            birdbird.publish.list_batches = original_list_batches

    def test_create_new_batch(self):
        """Test creating new batch sequence."""
        mock_client = MagicMock()

        from birdbird.publish import list_batches
        import birdbird.publish
        original_list_batches = birdbird.publish.list_batches

        def mock_list_batches(client, bucket):
            return ["20260114_02", "20260114_01"]

        birdbird.publish.list_batches = mock_list_batches

        try:
            batch_id, exists = generate_batch_id(
                mock_client, "test-bucket", "2026-01-14", create_new=True
            )

            # Should create new sequence (03)
            assert batch_id == "20260114_03"
            assert exists is False
        finally:
            birdbird.publish.list_batches = original_list_batches

    def test_unknown_date_fallback(self):
        """Test with unknown date falls back to today's date."""
        mock_client = MagicMock()

        from birdbird.publish import list_batches
        import birdbird.publish
        original_list_batches = birdbird.publish.list_batches

        def mock_list_batches(client, bucket):
            return []

        birdbird.publish.list_batches = mock_list_batches

        try:
            batch_id, exists = generate_batch_id(
                mock_client, "test-bucket", "unknown", create_new=False
            )

            # Should use today's date in YYYYMMDD format
            today = datetime.now().strftime("%Y%m%d")
            assert batch_id == f"{today}_01"
            assert exists is False
        finally:
            birdbird.publish.list_batches = original_list_batches

    def test_date_format_conversion(self):
        """Test date format conversion from YYYY-MM-DD to YYYYMMDD."""
        mock_client = MagicMock()

        from birdbird.publish import list_batches
        import birdbird.publish
        original_list_batches = birdbird.publish.list_batches

        def mock_list_batches(client, bucket):
            return []

        birdbird.publish.list_batches = mock_list_batches

        try:
            batch_id, exists = generate_batch_id(
                mock_client, "test-bucket", "2026-01-14", create_new=False
            )

            # Hyphens should be removed
            assert batch_id.startswith("20260114")
        finally:
            birdbird.publish.list_batches = original_list_batches
