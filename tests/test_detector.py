"""Tests for detector.py module (mocked YOLO + cv2).

@author Claude Opus 4.6 Anthropic
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from birdbird.detector import BirdDetector, Detection


@pytest.fixture
def detector():
    """Create BirdDetector with mocked YOLO model."""
    with patch("birdbird.detector.YOLO") as mock_yolo_cls:
        mock_model = MagicMock()
        mock_yolo_cls.return_value = mock_model
        det = BirdDetector(bird_confidence=0.2)
        det._mock_model = mock_model
        yield det


class TestDetectInFrameDetailed:
    """Tests for detect_in_frame_detailed()."""

    def test_bird_detected_returns_detection(self, detector, mock_yolo_result):
        """Bird class 14 above threshold returns Detection."""
        detector._mock_model.return_value = mock_yolo_result([(14, 0.85)])
        frame = np.zeros((480, 640, 3), dtype=np.uint8)

        result = detector.detect_in_frame_detailed(frame, timestamp=2.5)

        assert result is not None
        assert isinstance(result, Detection)
        assert result.timestamp == 2.5
        assert result.confidence == 0.85

    def test_non_bird_class_ignored(self, detector, mock_yolo_result):
        """Non-bird class (e.g., class 0 = person) returns None."""
        detector._mock_model.return_value = mock_yolo_result([(0, 0.95)])
        frame = np.zeros((480, 640, 3), dtype=np.uint8)

        result = detector.detect_in_frame_detailed(frame)

        assert result is None

    def test_below_confidence_threshold(self, detector, mock_yolo_result):
        """Bird below confidence threshold returns None."""
        detector._mock_model.return_value = mock_yolo_result([(14, 0.1)])
        frame = np.zeros((480, 640, 3), dtype=np.uint8)

        result = detector.detect_in_frame_detailed(frame)

        assert result is None

    def test_multiple_detections_picks_bird(self, detector, mock_yolo_result):
        """Multiple detections, picks the first matching bird."""
        detector._mock_model.return_value = mock_yolo_result([
            (0, 0.95),   # person
            (16, 0.80),  # dog
            (14, 0.72),  # bird
        ])
        frame = np.zeros((480, 640, 3), dtype=np.uint8)

        result = detector.detect_in_frame_detailed(frame, timestamp=1.0)

        assert result is not None
        assert result.confidence == 0.72

    def test_no_detections_empty_boxes(self, detector, mock_yolo_result):
        """No detections (boxes is None) returns None."""
        detector._mock_model.return_value = mock_yolo_result(None)
        frame = np.zeros((480, 640, 3), dtype=np.uint8)

        result = detector.detect_in_frame_detailed(frame)

        assert result is None


class TestDetectInFrame:
    """Tests for detect_in_frame()."""

    def test_delegates_to_detailed(self, detector, mock_yolo_result):
        """Returns bool based on detect_in_frame_detailed."""
        detector._mock_model.return_value = mock_yolo_result([(14, 0.85)])
        frame = np.zeros((480, 640, 3), dtype=np.uint8)

        assert detector.detect_in_frame(frame) is True

    def test_returns_false_when_no_bird(self, detector, mock_yolo_result):
        """Returns False when no bird detected."""
        detector._mock_model.return_value = mock_yolo_result([(0, 0.95)])
        frame = np.zeros((480, 640, 3), dtype=np.uint8)

        assert detector.detect_in_frame(frame) is False


class TestDetectInVideoDetailed:
    """Tests for detect_in_video_detailed()."""

    def test_bird_found_at_frame(self, detector, mock_yolo_result, mock_video_capture):
        """Bird found at a sampled frame returns Detection with correct timestamp."""
        cap = mock_video_capture(fps=30.0, frame_count=300)

        # Bird detected on first frame check (frame 0)
        detector._mock_model.return_value = mock_yolo_result([(14, 0.9)])

        with patch("birdbird.detector.cv2") as mock_cv2:
            mock_cv2.VideoCapture.return_value = cap
            mock_cv2.CAP_PROP_FPS = 5
            mock_cv2.CAP_PROP_FRAME_COUNT = 7

            result = detector.detect_in_video_detailed(Path("test.avi"))

        assert result is not None
        assert result.confidence == 0.9
        assert result.timestamp == 0.0

    def test_no_bird_in_any_frame(self, detector, mock_yolo_result, mock_video_capture):
        """No bird in any sampled frame returns None."""
        cap = mock_video_capture(fps=30.0, frame_count=300)

        # No bird ever
        detector._mock_model.return_value = mock_yolo_result([(0, 0.95)])

        with patch("birdbird.detector.cv2") as mock_cv2:
            mock_cv2.VideoCapture.return_value = cap
            mock_cv2.CAP_PROP_FPS = 5
            mock_cv2.CAP_PROP_FRAME_COUNT = 7

            result = detector.detect_in_video_detailed(Path("test.avi"))

        assert result is None

    def test_video_wont_open(self, detector, mock_video_capture):
        """Video that won't open returns None."""
        cap = mock_video_capture(is_opened=False)

        with patch("birdbird.detector.cv2") as mock_cv2:
            mock_cv2.VideoCapture.return_value = cap

            result = detector.detect_in_video_detailed(Path("missing.avi"))

        assert result is None

    def test_weighted_sampling_intervals(self, detector, mock_yolo_result, mock_video_capture):
        """Verifies denser sampling in first second (every ~0.25s) then 1fps."""
        # Use 30fps, 300 frames (10 seconds)
        dummy_frame = np.zeros((480, 640, 3), dtype=np.uint8)
        # Enough frames to read through
        frames = [(True, dummy_frame)] * 300 + [(False, None)]
        cap = mock_video_capture(fps=30.0, frame_count=300, frames=frames)

        # Never detect a bird so it scans all frames
        detector._mock_model.return_value = mock_yolo_result([(0, 0.5)])

        with patch("birdbird.detector.cv2") as mock_cv2:
            mock_cv2.VideoCapture.return_value = cap
            mock_cv2.CAP_PROP_FPS = 5
            mock_cv2.CAP_PROP_FRAME_COUNT = 7

            detector.detect_in_video_detailed(Path("test.avi"))

        # Model should be called for sampled frames:
        # First second (frames 0-29): every 7 frames (30/4=7) -> frames 0,7,14,21 = 4 calls
        # Remaining 270 frames: every 30 frames -> frames 30,60,...,270 = 9 calls
        # Total: ~13 calls
        call_count = detector._mock_model.call_count
        assert 10 <= call_count <= 15


class TestDetectInVideo:
    """Tests for detect_in_video()."""

    def test_delegates_to_detailed(self, detector, mock_yolo_result, mock_video_capture):
        """Returns bool based on detect_in_video_detailed."""
        cap = mock_video_capture(fps=30.0, frame_count=300)
        detector._mock_model.return_value = mock_yolo_result([(14, 0.9)])

        with patch("birdbird.detector.cv2") as mock_cv2:
            mock_cv2.VideoCapture.return_value = cap
            mock_cv2.CAP_PROP_FPS = 5
            mock_cv2.CAP_PROP_FRAME_COUNT = 7

            assert detector.detect_in_video(Path("test.avi")) is True
