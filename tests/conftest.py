"""Shared pytest fixtures for birdbird tests.

@author Claude Sonnet 4.5 Anthropic
"""

import sys
from unittest.mock import MagicMock

import numpy as np
import pytest

# Stub heavy ML packages that aren't installed in CI (they're mocked in individual tests).
# Must run at module level so the stub is in place when pytest collects test files.
# setdefault leaves the real package in place when running locally with full deps installed.
sys.modules.setdefault("ultralytics", MagicMock())


@pytest.fixture
def tmp_config_dir(tmp_path):
    """Create temporary ~/.birdbird/ directory."""
    config_dir = tmp_path / ".birdbird"
    config_dir.mkdir()
    return config_dir


@pytest.fixture
def sample_config():
    """Sample valid configuration dict."""
    return {
        "location": {
            "lat": 51.5074,
            "lon": -0.1278,
        },
        "species": {
            "enabled": True,
            "samples_per_minute": 6.0,
            "min_confidence": 0.5,
            "labels_file": "/path/to/labels.txt",
            "processing": {
                "mode": "remote",
                "remote": {
                    "host": "user@gpu-server.local",
                    "shell": "bash",
                    "python_env": "~/bioclip_env",
                    "timeout": 300,
                },
            },
        },
    }


@pytest.fixture
def tmp_input_dir(tmp_path):
    """Create temporary input directory with AVI structure."""
    input_dir = tmp_path / "20260114"
    input_dir.mkdir()

    # Create sample AVI files
    (input_dir / "1408301500.avi").touch()
    (input_dir / "1408301600.avi").touch()
    (input_dir / "1508301700.avi").touch()

    return input_dir


@pytest.fixture
def sample_detections():
    """Sample detection data for best_clips tests."""
    return [
        {
            "timestamp_s": 0.0,
            "species": "Blue Tit",
            "confidence": 0.9,
        },
        {
            "timestamp_s": 5.0,
            "species": "Blue Tit",
            "confidence": 0.85,
        },
        {
            "timestamp_s": 10.0,
            "species": "Robin",
            "confidence": 0.75,
        },
        {
            "timestamp_s": 15.0,
            "species": "Blue Tit",
            "confidence": 0.8,
        },
        {
            "timestamp_s": 100.0,
            "species": "Blue Tit",
            "confidence": 0.95,
        },
    ]


@pytest.fixture
def sample_clip_filenames():
    """Sample clip filenames for publish tests."""
    return [
        "1408301500.avi",
        "1408301600.avi",
        "1508301700.avi",
        "1608301800.avi",
    ]


@pytest.fixture
def sample_birdnet_csv(tmp_path):
    """Create sample BirdNET CSV file."""
    csv_path = tmp_path / "results.csv"
    csv_content = """Start (s),End (s),Scientific name,Common name,Confidence,File
0.0,3.0,Cyanistes caeruleus,Eurasian Blue Tit,0.9134,1408301500.wav
5.0,8.0,Erithacus rubecula,European Robin,0.8521,1408301500.wav
12.0,15.0,Parus major,Great Tit,0.7845,1408301500.wav
"""
    csv_path.write_text(csv_content)
    return csv_path


# --- Layer 2 shared fixtures ---


@pytest.fixture
def mock_yolo_result():
    """Factory for mock YOLO detection results.

    @author Claude Opus 4.6 Anthropic
    """

    def _make(detections=None):
        """Create mock YOLO result with given detections.

        Args:
            detections: List of (class_id, confidence) tuples.
                        None means no boxes at all.
        """
        result = MagicMock()
        if detections is None:
            result.boxes = None
            return [result]

        boxes = MagicMock()
        cls_list = [d[0] for d in detections]
        conf_list = [d[1] for d in detections]
        boxes.cls = cls_list
        boxes.conf = conf_list
        boxes.__len__ = lambda self: len(cls_list)

        # For frames.py: set up individual box iteration
        mock_boxes = []
        for i, (cls_id, conf) in enumerate(detections):
            box = MagicMock()
            box.cls = [cls_id]
            box.conf = [conf]
            # xyxy format: [x1, y1, x2, y2]
            xyxy_tensor = MagicMock()
            xyxy_tensor.cpu.return_value.numpy.return_value = np.array([100, 100, 300, 300])
            box.xyxy = [xyxy_tensor]
            mock_boxes.append(box)

        boxes.__iter__ = lambda self: iter(mock_boxes)
        result.boxes = boxes
        return [result]

    return _make


@pytest.fixture
def mock_video_capture():
    """Factory for mock cv2.VideoCapture with configurable frames/properties.

    @author Claude Opus 4.6 Anthropic
    """

    def _make(
        is_opened=True,
        fps=30.0,
        frame_count=300,
        frames=None,
    ):
        """Create mock VideoCapture.

        Args:
            is_opened: Whether isOpened() returns True
            fps: Frames per second
            frame_count: Total frame count
            frames: List of (success, frame) tuples for read() calls.
                    If None, generates dummy frames.
        """
        cap = MagicMock()
        cap.isOpened.return_value = is_opened

        def get_prop(prop_id):
            # cv2.CAP_PROP_FPS = 5, CAP_PROP_FRAME_COUNT = 7
            if prop_id == 5:
                return fps
            if prop_id == 7:
                return float(frame_count)
            return 0.0

        cap.get.side_effect = get_prop

        if frames is not None:
            cap.read.side_effect = frames
        else:
            # Default: return dummy frames then stop
            dummy_frame = np.zeros((480, 640, 3), dtype=np.uint8)
            read_results = [(True, dummy_frame)] * frame_count + [(False, None)]
            cap.read.side_effect = read_results

        return cap

    return _make


@pytest.fixture
def mock_s3_client():
    """Mock boto3 S3 client with configurable responses.

    @author Claude Opus 4.6 Anthropic
    """
    client = MagicMock()
    return client
