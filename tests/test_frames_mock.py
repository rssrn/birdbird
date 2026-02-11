"""Tests for frames.py module (mocked cv2 + BirdDetector).

@author Claude Opus 4.6 Anthropic
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from birdbird.frames import (
    FrameScore,
    calculate_bird_size,
    calculate_position,
    calculate_sharpness,
    extract_and_score_frames,
    normalize_scores,
)


class TestCalculateSharpness:
    """Tests for calculate_sharpness()."""

    def test_synthetic_frame(self):
        """Returns Laplacian variance for a synthetic frame."""
        # Create a frame with edges (high sharpness)
        frame = np.zeros((100, 100, 3), dtype=np.uint8)
        frame[40:60, 40:60] = 255  # White square creates edges

        with patch("birdbird.frames.cv2") as mock_cv2:
            # Simulate grayscale conversion and Laplacian
            gray = np.mean(frame, axis=2)
            mock_cv2.COLOR_BGR2GRAY = 6
            mock_cv2.CV_64F = 6
            mock_cv2.cvtColor.return_value = gray

            laplacian = MagicMock()
            laplacian.var.return_value = 42.5
            mock_cv2.Laplacian.return_value = laplacian

            result = calculate_sharpness(frame)

        assert result == 42.5
        mock_cv2.cvtColor.assert_called_once()
        mock_cv2.Laplacian.assert_called_once()


class TestCalculateBirdSize:
    """Tests for calculate_bird_size()."""

    def test_bird_detected_with_bbox(self, mock_yolo_result):
        """Returns area ratio when bird detected."""
        detector = MagicMock()
        detector.BIRD_CLASS_ID = 14
        detector.bird_confidence = 0.2

        # Frame 640x480 = 307200 pixels
        frame = np.zeros((480, 640, 3), dtype=np.uint8)

        # Create mock result with bird bbox
        result_mock = MagicMock()
        box = MagicMock()
        box.cls = [14]
        box.conf = [0.85]
        # bbox 200x200 = 40000 pixels
        xyxy_tensor = MagicMock()
        xyxy_tensor.cpu.return_value.numpy.return_value = np.array([100, 100, 300, 300])
        box.xyxy = [xyxy_tensor]

        boxes = MagicMock()
        boxes.__len__ = lambda self: 1
        boxes.__iter__ = lambda self: iter([box])
        result_mock.boxes = boxes

        detector.model.return_value = [result_mock]

        result = calculate_bird_size(detector, frame)

        # 200*200 / (640*480) ≈ 0.1302
        assert result == pytest.approx(40000 / 307200, rel=1e-3)

    def test_no_detection(self, mock_yolo_result):
        """Returns 0.0 when no detection."""
        detector = MagicMock()
        detector.BIRD_CLASS_ID = 14
        detector.bird_confidence = 0.2

        result_mock = MagicMock()
        result_mock.boxes = None
        detector.model.return_value = [result_mock]

        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        result = calculate_bird_size(detector, frame)

        assert result == 0.0


class TestCalculatePosition:
    """Tests for calculate_position()."""

    def test_bird_not_touching_edges(self):
        """Returns 1.0 when bird is clear of edges."""
        detector = MagicMock()
        detector.BIRD_CLASS_ID = 14
        detector.bird_confidence = 0.2

        frame = np.zeros((480, 640, 3), dtype=np.uint8)

        result_mock = MagicMock()
        box = MagicMock()
        box.cls = [14]
        box.conf = [0.85]
        # bbox well inside frame
        xyxy_tensor = MagicMock()
        xyxy_tensor.cpu.return_value.numpy.return_value = np.array([100, 100, 300, 300])
        box.xyxy = [xyxy_tensor]

        boxes = MagicMock()
        boxes.__len__ = lambda self: 1
        boxes.__iter__ = lambda self: iter([box])
        result_mock.boxes = boxes
        detector.model.return_value = [result_mock]

        result = calculate_position(detector, frame)

        assert result == 1.0

    def test_bird_touching_left_edge(self):
        """Returns 0.3 when bird touches left edge."""
        detector = MagicMock()
        detector.BIRD_CLASS_ID = 14
        detector.bird_confidence = 0.2

        frame = np.zeros((480, 640, 3), dtype=np.uint8)

        result_mock = MagicMock()
        box = MagicMock()
        box.cls = [14]
        box.conf = [0.85]
        # bbox touching left edge (x1=5 < threshold=10)
        xyxy_tensor = MagicMock()
        xyxy_tensor.cpu.return_value.numpy.return_value = np.array([5, 100, 200, 300])
        box.xyxy = [xyxy_tensor]

        boxes = MagicMock()
        boxes.__len__ = lambda self: 1
        boxes.__iter__ = lambda self: iter([box])
        result_mock.boxes = boxes
        detector.model.return_value = [result_mock]

        result = calculate_position(detector, frame)

        assert result == 0.3

    def test_no_detection(self):
        """Returns 0.0 when no detection."""
        detector = MagicMock()
        detector.BIRD_CLASS_ID = 14
        detector.bird_confidence = 0.2

        result_mock = MagicMock()
        result_mock.boxes = None
        detector.model.return_value = [result_mock]

        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        result = calculate_position(detector, frame)

        assert result == 0.0


class TestNormalizeScores:
    """Tests for normalize_scores()."""

    def test_varied_values(self):
        """Min maps to 0, max maps to 1."""
        scores = {"sharpness": [10.0, 50.0, 100.0]}

        result = normalize_scores(scores)

        assert result["sharpness"][0] == pytest.approx(0.0)
        assert result["sharpness"][1] == pytest.approx(40.0 / 90.0)
        assert result["sharpness"][2] == pytest.approx(1.0)

    def test_all_same_values(self):
        """All same values map to 0.5."""
        scores = {"sharpness": [50.0, 50.0, 50.0]}

        result = normalize_scores(scores)

        assert all(v == 0.5 for v in result["sharpness"])

    def test_confidence_key_skipped(self):
        """Confidence values are not normalized (already 0-1)."""
        scores = {"confidence": [0.2, 0.5, 0.9]}

        result = normalize_scores(scores)

        assert result["confidence"] == [0.2, 0.5, 0.9]


class TestExtractAndScoreFrames:
    """Tests for extract_and_score_frames()."""

    def test_multiple_clips(self, tmp_path):
        """Returns sorted FrameScores for multiple clips."""
        # Set up paths structure
        input_dir = tmp_path / "20260114"
        input_dir.mkdir()
        birdbird_dir = input_dir / "birdbird"
        working_dir = birdbird_dir / "working" / "filter"
        clips_dir = working_dir / "clips"
        clips_dir.mkdir(parents=True)

        # Create detections.json
        detections = {
            "clip1.avi": {"first_bird": 1.0, "confidence": 0.9},
            "clip2.avi": {"first_bird": 2.0, "confidence": 0.7},
        }
        detections_path = working_dir / "detections.json"
        detections_path.write_text(json.dumps(detections))

        # Create clip files
        (clips_dir / "clip1.avi").touch()
        (clips_dir / "clip2.avi").touch()

        # Mock detector
        detector = MagicMock()
        detector.BIRD_CLASS_ID = 14
        detector.bird_confidence = 0.2

        # Mock YOLO results for bird_size and position
        result_mock = MagicMock()
        box = MagicMock()
        box.cls = [14]
        box.conf = [0.85]
        xyxy_tensor = MagicMock()
        xyxy_tensor.cpu.return_value.numpy.return_value = np.array([100, 100, 300, 300])
        box.xyxy = [xyxy_tensor]
        boxes = MagicMock()
        boxes.__len__ = lambda self: 1
        boxes.__iter__ = lambda self: iter([box])
        result_mock.boxes = boxes
        detector.model.return_value = [result_mock]

        weights = {
            "confidence": 0.25,
            "sharpness": 0.25,
            "bird_size": 0.25,
            "position": 0.25,
        }

        dummy_frame = np.zeros((480, 640, 3), dtype=np.uint8)
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = True
        mock_cap.get.side_effect = lambda prop: 30.0 if prop == 5 else 0.0
        mock_cap.read.return_value = (True, dummy_frame)

        with patch("birdbird.frames.cv2") as mock_cv2:
            mock_cv2.VideoCapture.return_value = mock_cap
            mock_cv2.CAP_PROP_FPS = 5
            mock_cv2.COLOR_BGR2GRAY = 6
            mock_cv2.CV_64F = 6
            mock_cv2.cvtColor.return_value = np.zeros((480, 640), dtype=np.uint8)

            laplacian = MagicMock()
            laplacian.var.return_value = 100.0
            mock_cv2.Laplacian.return_value = laplacian

            from birdbird.paths import BirdbirdPaths
            paths = BirdbirdPaths.from_input_dir(input_dir)

            scored, timing = extract_and_score_frames(
                input_dir, detector, weights, paths=paths,
            )

        assert len(scored) == 2
        # Should be sorted by combined score (descending)
        assert scored[0].combined >= scored[1].combined
        assert all(isinstance(s, FrameScore) for s in scored)
        assert "total_frames_scored" in timing

    def test_empty_detections(self, tmp_path):
        """Returns empty list when no detections."""
        input_dir = tmp_path / "20260114"
        input_dir.mkdir()
        birdbird_dir = input_dir / "birdbird"
        working_dir = birdbird_dir / "working" / "filter"
        working_dir.mkdir(parents=True)

        # Empty detections
        detections_path = working_dir / "detections.json"
        detections_path.write_text("{}")

        detector = MagicMock()
        weights = {"confidence": 0.25, "sharpness": 0.25, "bird_size": 0.25, "position": 0.25}

        from birdbird.paths import BirdbirdPaths
        paths = BirdbirdPaths.from_input_dir(input_dir)

        scored, timing = extract_and_score_frames(
            input_dir, detector, weights, paths=paths,
        )

        assert scored == []
        assert timing == {}
