"""Tests for frames.py module (mocked cv2 + BirdDetector).

@author Claude Opus 4.6 Anthropic
"""

import json
from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pytest

from birdbird.frames import (
    FrameScore,
    calculate_bird_size,
    calculate_position,
    calculate_sharpness,
    copy_top_frames_to_assets,
    extract_and_score_frames,
    normalize_scores,
    save_frame_metadata,
    save_top_frames,
)


class TestCalculateSharpness:
    """Tests for calculate_sharpness()."""

    def test_synthetic_frame(self, mocker):
        """Returns Laplacian variance for a synthetic frame."""
        # Create a frame with edges (high sharpness)
        frame = np.zeros((100, 100, 3), dtype=np.uint8)
        frame[40:60, 40:60] = 255  # White square creates edges

        mock_cv2 = mocker.patch("birdbird.frames.cv2")
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

    def test_multiple_clips(self, tmp_path, mocker):
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

        mock_cv2 = mocker.patch("birdbird.frames.cv2")
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
            input_dir,
            detector,
            weights,
            paths=paths,
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
            input_dir,
            detector,
            weights,
            paths=paths,
        )

        assert scored == []
        assert timing == {}


def _make_frame_score(
    clip_name="clip.avi", timestamp=1.0, confidence=0.9, sharpness=100.0, bird_size=0.1, position=1.0, combined=0.8
):
    return FrameScore(
        clip_name=clip_name,
        timestamp=timestamp,
        confidence=confidence,
        sharpness=sharpness,
        bird_size=bird_size,
        position=position,
        combined=combined,
    )


class TestSaveFrameMetadata:
    """Tests for save_frame_metadata().

    @author Claude Sonnet 4.6 Anthropic
    """

    def test_json_structure_has_required_top_level_keys(self, tmp_path):
        """Written JSON has frames, timing_stats, and config keys."""
        frames = [_make_frame_score()]
        output_path = tmp_path / "frame_scores.json"

        save_frame_metadata(frames, {"total_frames_scored": 1}, output_path, {"top_n": 10})

        data = json.loads(output_path.read_text())
        assert set(data.keys()) == {"frames", "timing_stats", "config"}

    def test_frame_entry_has_required_fields(self, tmp_path):
        """Each frame entry has rank, filename, clip, timestamp, and scores."""
        frames = [_make_frame_score(clip_name="clip.avi", timestamp=2.5)]
        output_path = tmp_path / "frame_scores.json"

        save_frame_metadata(frames, {}, output_path, {})

        entry = json.loads(output_path.read_text())["frames"][0]
        assert entry["rank"] == 1
        assert entry["clip"] == "clip.avi"
        assert entry["timestamp"] == 2.5
        assert set(entry["scores"].keys()) == {"confidence", "sharpness", "bird_size", "position", "combined"}

    def test_filename_format(self, tmp_path):
        """Filename matches expected pattern: frame_NNN_clipbase_Xs_score_S.SS.jpg"""
        frames = [_make_frame_score(clip_name="clip01.avi", timestamp=3.0, combined=0.85)]
        output_path = tmp_path / "frame_scores.json"

        save_frame_metadata(frames, {}, output_path, {})

        entry = json.loads(output_path.read_text())["frames"][0]
        assert entry["filename"] == "frame_001_clip01_3.0s_score_0.85.jpg"

    def test_scores_rounded_correctly(self, tmp_path):
        """Scores are rounded: confidence/bird_size/position/combined to 3dp, sharpness to 1dp."""
        frames = [
            _make_frame_score(
                confidence=0.91234, sharpness=123.456, bird_size=0.12345, position=0.99999, combined=0.87654
            )
        ]
        output_path = tmp_path / "frame_scores.json"

        save_frame_metadata(frames, {}, output_path, {})

        scores = json.loads(output_path.read_text())["frames"][0]["scores"]
        assert scores["confidence"] == 0.912
        assert scores["sharpness"] == 123.5
        assert scores["bird_size"] == 0.123
        assert scores["position"] == 1.0
        assert scores["combined"] == 0.877

    def test_rank_increments_per_frame(self, tmp_path):
        """Multiple frames get sequential rank values starting at 1."""
        frames = [_make_frame_score(combined=0.9), _make_frame_score(combined=0.7), _make_frame_score(combined=0.5)]
        output_path = tmp_path / "frame_scores.json"

        save_frame_metadata(frames, {}, output_path, {})

        entries = json.loads(output_path.read_text())["frames"]
        assert [e["rank"] for e in entries] == [1, 2, 3]


class TestSaveTopFrames:
    """Tests for save_top_frames().

    @author Claude Sonnet 4.6 Anthropic
    """

    def test_correct_filename_generated(self, tmp_path, mocker):
        """Saves JPEG with expected descriptive filename."""
        clips_dir = tmp_path / "clips"
        clips_dir.mkdir()
        output_dir = tmp_path / "frames"
        output_dir.mkdir()
        (clips_dir / "clip.avi").write_bytes(b"fake")

        frames = [_make_frame_score(clip_name="clip.avi", timestamp=1.0, combined=0.85)]

        dummy_frame = np.zeros((480, 640, 3), dtype=np.uint8)
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = True
        mock_cap.get.return_value = 30.0
        mock_cap.read.return_value = (True, dummy_frame)

        mock_cv2 = mocker.patch("birdbird.frames.cv2")
        mock_cv2.VideoCapture.return_value = mock_cap
        mock_cv2.CAP_PROP_FPS = 5
        mock_cv2.CAP_PROP_POS_FRAMES = 1
        mock_cv2.IMWRITE_JPEG_QUALITY = 1
        mock_cv2.imwrite.return_value = True

        result = save_top_frames(frames, clips_dir, output_dir, top_n=1)

        assert len(result) == 1
        assert result[0].name == "frame_001_clip_1.0s_score_0.85.jpg"

    def test_saves_with_quality_95(self, tmp_path, mocker):
        """Calls cv2.imwrite with JPEG quality 95."""
        clips_dir = tmp_path / "clips"
        clips_dir.mkdir()
        output_dir = tmp_path / "frames"
        output_dir.mkdir()
        (clips_dir / "clip.avi").write_bytes(b"fake")

        frames = [_make_frame_score()]
        dummy_frame = np.zeros((480, 640, 3), dtype=np.uint8)
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = True
        mock_cap.get.return_value = 30.0
        mock_cap.read.return_value = (True, dummy_frame)

        mock_cv2 = mocker.patch("birdbird.frames.cv2")
        mock_cv2.VideoCapture.return_value = mock_cap
        mock_cv2.CAP_PROP_FPS = 5
        mock_cv2.CAP_PROP_POS_FRAMES = 1
        mock_cv2.IMWRITE_JPEG_QUALITY = 1
        mock_cv2.imwrite.return_value = True

        save_top_frames(frames, clips_dir, output_dir, top_n=1)

        mock_cv2.imwrite.assert_called_once()
        _, _, params = mock_cv2.imwrite.call_args[0]
        assert params == [mock_cv2.IMWRITE_JPEG_QUALITY, 95]

    def test_skips_missing_clip(self, tmp_path, mocker):
        """Returns empty list when clip file does not exist."""
        clips_dir = tmp_path / "clips"
        clips_dir.mkdir()
        output_dir = tmp_path / "frames"
        output_dir.mkdir()
        # Intentionally not creating clips_dir / "missing.avi"

        frames = [_make_frame_score(clip_name="missing.avi")]
        mocker.patch("birdbird.frames.cv2")

        result = save_top_frames(frames, clips_dir, output_dir, top_n=1)

        assert result == []

    def test_respects_top_n_limit(self, tmp_path, mocker):
        """Only saves top_n frames even when more are provided."""
        clips_dir = tmp_path / "clips"
        clips_dir.mkdir()
        output_dir = tmp_path / "frames"
        output_dir.mkdir()
        for i in range(5):
            (clips_dir / f"clip_{i}.avi").write_bytes(b"fake")

        frames = [_make_frame_score(clip_name=f"clip_{i}.avi", combined=1.0 - i * 0.1) for i in range(5)]
        dummy_frame = np.zeros((480, 640, 3), dtype=np.uint8)
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = True
        mock_cap.get.return_value = 30.0
        mock_cap.read.return_value = (True, dummy_frame)

        mock_cv2 = mocker.patch("birdbird.frames.cv2")
        mock_cv2.VideoCapture.return_value = mock_cap
        mock_cv2.CAP_PROP_FPS = 5
        mock_cv2.CAP_PROP_POS_FRAMES = 1
        mock_cv2.IMWRITE_JPEG_QUALITY = 1
        mock_cv2.imwrite.return_value = True

        result = save_top_frames(frames, clips_dir, output_dir, top_n=2)

        assert len(result) == 2


class TestCopyTopFramesToAssets:
    """Tests for copy_top_frames_to_assets().

    @author Claude Sonnet 4.6 Anthropic
    """

    def _make_frame_scores_json(self, candidates_dir: Path, filenames: list[str]) -> Path:
        """Create frame_scores.json and matching candidate files."""
        data = {"frames": [{"filename": name, "rank": i + 1} for i, name in enumerate(filenames)]}
        path = candidates_dir.parent / "frame_scores.json"
        path.write_text(json.dumps(data))
        for name in filenames:
            (candidates_dir / name).write_bytes(b"fake jpeg")
        return path

    def test_copies_correct_number_of_files(self, tmp_path):
        """Copies exactly top_n files to assets dir."""
        candidates_dir = tmp_path / "candidates"
        candidates_dir.mkdir()
        assets_dir = tmp_path / "assets"
        assets_dir.mkdir()

        names = [f"frame_{i:03d}_clip_{i}.jpg" for i in range(1, 4)]
        scores_path = self._make_frame_scores_json(candidates_dir, names)

        result = copy_top_frames_to_assets(scores_path, candidates_dir, assets_dir, top_n=3)

        assert len(result) == 3
        assert all(p.exists() for p in result)

    def test_reads_frame_scores_json_correctly(self, tmp_path):
        """Uses first top_n entries from frame_scores.json, ignoring the rest."""
        candidates_dir = tmp_path / "candidates"
        candidates_dir.mkdir()
        assets_dir = tmp_path / "assets"
        assets_dir.mkdir()

        names = [f"frame_{i:03d}_clip_{i}.jpg" for i in range(1, 6)]
        scores_path = self._make_frame_scores_json(candidates_dir, names)

        result = copy_top_frames_to_assets(scores_path, candidates_dir, assets_dir, top_n=2)

        assert len(result) == 2

    def test_handles_missing_source_gracefully(self, tmp_path):
        """Does not raise when a source file is missing; returns asset paths."""
        candidates_dir = tmp_path / "candidates"
        candidates_dir.mkdir()
        assets_dir = tmp_path / "assets"
        assets_dir.mkdir()

        data = {"frames": [{"filename": "missing.jpg", "rank": 1}]}
        scores_path = tmp_path / "frame_scores.json"
        scores_path.write_text(json.dumps(data))
        # Intentionally no file at candidates_dir / "missing.jpg"

        result = copy_top_frames_to_assets(scores_path, candidates_dir, assets_dir, top_n=1)

        # Returns the asset path list even if nothing was copied
        assert len(result) == 1
        assert not result[0].exists()
