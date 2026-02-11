"""Tests for filter.py module (mocked BirdDetector + filesystem).

@author Claude Opus 4.6 Anthropic
"""

import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from birdbird.detector import Detection
from birdbird.filter import create_symlink_or_copy, filter_clips


class TestCreateSymlinkOrCopy:
    """Tests for create_symlink_or_copy()."""

    def test_symlink_succeeds(self, tmp_path):
        """Creates symlink when os.symlink works."""
        src = tmp_path / "source.avi"
        src.touch()
        dst = tmp_path / "link.avi"

        create_symlink_or_copy(src, dst)

        assert dst.is_symlink()
        assert dst.resolve() == src.resolve()

    def test_symlink_fails_falls_back_to_copy(self, tmp_path):
        """Falls back to copy when symlink raises OSError."""
        src = tmp_path / "source.avi"
        src.write_bytes(b"test data")
        dst = tmp_path / "copy.avi"

        with patch("birdbird.filter.os.symlink", side_effect=OSError("not supported")):
            create_symlink_or_copy(src, dst)

        assert dst.exists()
        assert not dst.is_symlink()
        assert dst.read_bytes() == b"test data"


class TestFilterClips:
    """Tests for filter_clips()."""

    def _make_clips_dir(self, tmp_path, num_clips=3):
        """Create a temp directory with .avi files."""
        input_dir = tmp_path / "20260114"
        input_dir.mkdir()
        for i in range(num_clips):
            (input_dir / f"140830{i:02d}00.avi").touch()
        return input_dir

    @patch("birdbird.filter.BirdDetector")
    def test_some_clips_have_birds(self, mock_detector_cls, tmp_path):
        """Clips with birds get symlinked, stats are correct."""
        input_dir = self._make_clips_dir(tmp_path, 3)

        mock_detector = MagicMock()
        mock_detector_cls.return_value = mock_detector

        # First clip has bird, second doesn't, third has bird
        mock_detector.detect_in_video_detailed.side_effect = [
            Detection(timestamp=1.5, confidence=0.85),
            None,
            Detection(timestamp=0.5, confidence=0.72),
        ]

        stats = filter_clips(input_dir, bird_confidence=0.2)

        assert stats["total"] == 3
        assert stats["with_birds"] == 2
        assert stats["filtered_out"] == 1

        # Check detections.json was written
        detections_path = stats["paths"].detections_json
        assert detections_path.exists()
        with open(detections_path) as f:
            detections = json.load(f)
        assert len(detections) == 2

    @patch("birdbird.filter.BirdDetector")
    def test_no_clips_have_birds(self, mock_detector_cls, tmp_path):
        """No birds detected results in 0 with_birds."""
        input_dir = self._make_clips_dir(tmp_path, 2)

        mock_detector = MagicMock()
        mock_detector_cls.return_value = mock_detector
        mock_detector.detect_in_video_detailed.return_value = None

        stats = filter_clips(input_dir, bird_confidence=0.2)

        assert stats["with_birds"] == 0
        assert stats["filtered_out"] == 2

        # detections.json should be empty dict
        with open(stats["paths"].detections_json) as f:
            assert json.load(f) == {}

    @patch("birdbird.filter.BirdDetector")
    def test_all_clips_have_birds(self, mock_detector_cls, tmp_path):
        """All clips detected results in matching with_birds and total."""
        input_dir = self._make_clips_dir(tmp_path, 3)

        mock_detector = MagicMock()
        mock_detector_cls.return_value = mock_detector
        mock_detector.detect_in_video_detailed.return_value = Detection(
            timestamp=1.0, confidence=0.9
        )

        stats = filter_clips(input_dir)

        assert stats["with_birds"] == stats["total"] == 3
        assert stats["filtered_out"] == 0

    @patch("birdbird.filter.BirdDetector")
    def test_limit_parameter(self, mock_detector_cls, tmp_path):
        """Limit restricts number of clips processed."""
        input_dir = self._make_clips_dir(tmp_path, 5)

        mock_detector = MagicMock()
        mock_detector_cls.return_value = mock_detector
        mock_detector.detect_in_video_detailed.return_value = Detection(
            timestamp=1.0, confidence=0.9
        )

        stats = filter_clips(input_dir, limit=2)

        assert stats["total"] == 2
        assert mock_detector.detect_in_video_detailed.call_count == 2

    @patch("birdbird.filter.BirdDetector")
    def test_detections_json_format(self, mock_detector_cls, tmp_path):
        """Detections.json contains first_bird and confidence per clip."""
        input_dir = self._make_clips_dir(tmp_path, 1)

        mock_detector = MagicMock()
        mock_detector_cls.return_value = mock_detector
        mock_detector.detect_in_video_detailed.return_value = Detection(
            timestamp=2.5, confidence=0.873
        )

        stats = filter_clips(input_dir)

        with open(stats["paths"].detections_json) as f:
            detections = json.load(f)

        clip_name = list(detections.keys())[0]
        entry = detections[clip_name]
        assert "first_bird" in entry
        assert entry["first_bird"] == 2.5
        assert "confidence" in entry
        assert entry["confidence"] == 0.873
