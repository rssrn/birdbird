"""Tests for highlights.py module (mocked subprocess + cv2 + BirdDetector).

@author Claude Opus 4.6 Anthropic
"""

from pathlib import Path
from unittest.mock import MagicMock, patch, call

import numpy as np
import pytest

from birdbird.highlights import (
    Segment,
    _hardware_encoder_cache,
    concatenate_segments,
    detect_hardware_encoder,
    extract_segment,
    find_bird_segments,
    get_video_duration,
    _binary_search_entry,
    _binary_search_exit,
)


@pytest.fixture(autouse=True)
def reset_hw_encoder_cache():
    """Reset hardware encoder cache before each test."""
    import birdbird.highlights
    birdbird.highlights._hardware_encoder_cache = None
    yield
    birdbird.highlights._hardware_encoder_cache = None


class TestDetectHardwareEncoder:
    """Tests for detect_hardware_encoder()."""

    def test_encoder_available_and_works(self):
        """Returns encoder name when available and test passes."""
        encoders_result = MagicMock(stdout="h264_qsv h264_vaapi", returncode=0)
        test_result = MagicMock(returncode=0)

        with patch("birdbird.highlights.subprocess.run", side_effect=[encoders_result, test_result]):
            result = detect_hardware_encoder()

        assert result == "h264_qsv"

    def test_encoder_listed_but_test_fails(self):
        """Tries next encoder when test fails, returns None if all fail."""
        encoders_result = MagicMock(stdout="h264_qsv h264_vaapi", returncode=0)
        test_fail = MagicMock(returncode=1)

        with patch("birdbird.highlights.subprocess.run", side_effect=[encoders_result, test_fail, test_fail]):
            result = detect_hardware_encoder()

        assert result is None

    def test_ffmpeg_not_found(self):
        """Returns None when ffmpeg is not found."""
        with patch("birdbird.highlights.subprocess.run", side_effect=FileNotFoundError):
            result = detect_hardware_encoder()

        assert result is None


class TestGetVideoDuration:
    """Tests for get_video_duration()."""

    def test_valid_video(self, mock_video_capture):
        """Returns frames/fps for a valid video."""
        cap = mock_video_capture(fps=30.0, frame_count=300)

        with patch("birdbird.highlights.cv2") as mock_cv2:
            mock_cv2.VideoCapture.return_value = cap
            mock_cv2.CAP_PROP_FPS = 5
            mock_cv2.CAP_PROP_FRAME_COUNT = 7

            duration = get_video_duration(Path("test.avi"))

        assert duration == pytest.approx(10.0)

    def test_video_wont_open(self, mock_video_capture):
        """Returns 0.0 when video won't open."""
        cap = mock_video_capture(is_opened=False)

        with patch("birdbird.highlights.cv2") as mock_cv2:
            mock_cv2.VideoCapture.return_value = cap

            duration = get_video_duration(Path("missing.avi"))

        assert duration == 0.0


class TestBinarySearchEntry:
    """Tests for _binary_search_entry()."""

    def test_converges_to_correct_entry_point(self):
        """Binary search converges to the first bird time."""
        cap = MagicMock()
        detector = MagicMock()

        # Bird appears at time >= 3.0
        def detect_at_time(cap, det, time_sec, fps):
            return time_sec >= 3.0

        with patch("birdbird.highlights._detect_at_time", side_effect=detect_at_time):
            result = _binary_search_entry(cap, detector, 0.0, 5.0, 30.0, precision=0.5)

        # Should converge near 3.0
        assert 2.5 <= result <= 3.5


class TestBinarySearchExit:
    """Tests for _binary_search_exit()."""

    def test_converges_to_correct_exit_point(self):
        """Binary search converges to the last bird time."""
        cap = MagicMock()
        detector = MagicMock()

        # Bird visible until time <= 7.0
        def detect_at_time(cap, det, time_sec, fps):
            return time_sec <= 7.0

        with patch("birdbird.highlights._detect_at_time", side_effect=detect_at_time):
            result = _binary_search_exit(cap, detector, 3.0, 10.0, 30.0, precision=0.5)

        assert 6.5 <= result <= 7.5


class TestFindBirdSegments:
    """Tests for find_bird_segments()."""

    def test_with_known_first_bird(self, mock_video_capture):
        """Known first bird skips start search, finds end."""
        cap = mock_video_capture(fps=30.0, frame_count=300)
        detector = MagicMock()

        with patch("birdbird.highlights.cv2") as mock_cv2:
            mock_cv2.VideoCapture.return_value = cap
            mock_cv2.CAP_PROP_FPS = 5
            mock_cv2.CAP_PROP_FRAME_COUNT = 7

            # Bird still visible at end_time check
            with patch("birdbird.highlights._detect_at_time", return_value=True):
                segments = find_bird_segments(
                    Path("test.avi"), detector,
                    buffer_before=1.0, buffer_after=1.0,
                    known_first_bird=2.0,
                )

        assert len(segments) == 1
        assert segments[0].start_time == pytest.approx(1.0)  # 2.0 - 1.0 buffer

    def test_no_bird_detected(self, mock_video_capture):
        """No bird at any check time returns empty list."""
        cap = mock_video_capture(fps=30.0, frame_count=300)
        detector = MagicMock()

        with patch("birdbird.highlights.cv2") as mock_cv2:
            mock_cv2.VideoCapture.return_value = cap
            mock_cv2.CAP_PROP_FPS = 5
            mock_cv2.CAP_PROP_FRAME_COUNT = 7

            with patch("birdbird.highlights._detect_at_time", return_value=False):
                segments = find_bird_segments(Path("test.avi"), detector)

        assert segments == []

    def test_video_too_short(self, mock_video_capture):
        """Video with < 1 second returns empty list."""
        cap = mock_video_capture(fps=30.0, frame_count=10)
        detector = MagicMock()

        with patch("birdbird.highlights.cv2") as mock_cv2:
            mock_cv2.VideoCapture.return_value = cap
            mock_cv2.CAP_PROP_FPS = 5
            mock_cv2.CAP_PROP_FRAME_COUNT = 7

            segments = find_bird_segments(Path("test.avi"), detector)

        assert segments == []


class TestExtractSegment:
    """Tests for extract_segment()."""

    def test_software_encoder(self):
        """Software encoder builds correct ffmpeg command."""
        segment = Segment(clip_path=Path("clip.avi"), start_time=1.0, end_time=5.0)

        with patch("birdbird.highlights.detect_hardware_encoder", return_value=None):
            with patch("birdbird.highlights.subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=0, stderr="")

                result = extract_segment(segment, Path("out.mp4"))

        assert result is True
        cmd = mock_run.call_args[0][0]
        assert "libx264" in cmd
        assert "-ss" in cmd
        assert "1.0" in cmd

    def test_hardware_encoder(self):
        """Hardware encoder is used when available."""
        segment = Segment(clip_path=Path("clip.avi"), start_time=1.0, end_time=5.0)

        with patch("birdbird.highlights.detect_hardware_encoder", return_value="h264_qsv"):
            with patch("birdbird.highlights.subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=0, stderr="")

                result = extract_segment(segment, Path("out.mp4"))

        assert result is True
        cmd = mock_run.call_args[0][0]
        assert "h264_qsv" in cmd

    def test_hw_fails_falls_back_to_software(self):
        """Hardware encoder failure triggers software fallback."""
        segment = Segment(clip_path=Path("clip.avi"), start_time=1.0, end_time=5.0)

        with patch("birdbird.highlights.detect_hardware_encoder", return_value="h264_qsv"):
            with patch("birdbird.highlights.subprocess.run") as mock_run:
                # First call (hw) fails, second (sw) succeeds
                mock_run.side_effect = [
                    MagicMock(returncode=1, stderr="hw error"),
                    MagicMock(returncode=0, stderr=""),
                ]

                result = extract_segment(segment, Path("out.mp4"))

        assert result is True
        assert mock_run.call_count == 2
        fallback_cmd = mock_run.call_args_list[1][0][0]
        assert "libx264" in fallback_cmd

    def test_optimize_web_flag(self):
        """optimize_web adds fps filter."""
        segment = Segment(clip_path=Path("clip.avi"), start_time=0.0, end_time=3.0)

        with patch("birdbird.highlights.detect_hardware_encoder", return_value=None):
            with patch("birdbird.highlights.subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=0, stderr="")

                extract_segment(segment, Path("out.mp4"), optimize_web=True)

        cmd = mock_run.call_args[0][0]
        assert "-vf" in cmd
        vf_idx = cmd.index("-vf")
        assert cmd[vf_idx + 1] == "fps=24"


class TestConcatenateSegments:
    """Tests for concatenate_segments()."""

    def test_single_segment(self, tmp_path):
        """Single segment uses copy mode."""
        seg_file = tmp_path / "seg.mp4"
        seg_file.touch()

        with patch("birdbird.highlights.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)

            result = concatenate_segments([seg_file], tmp_path / "out.mp4")

        assert result is True
        cmd = mock_run.call_args[0][0]
        assert "-c" in cmd
        assert "copy" in cmd
        # Should not use concat demuxer
        assert "-f" not in cmd or "concat" not in cmd

    def test_multiple_segments(self, tmp_path):
        """Multiple segments creates concat list file."""
        seg_files = []
        for i in range(3):
            f = tmp_path / f"seg_{i}.mp4"
            f.touch()
            seg_files.append(f)

        with patch("birdbird.highlights.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)

            result = concatenate_segments(seg_files, tmp_path / "out.mp4")

        assert result is True
        cmd = mock_run.call_args[0][0]
        assert "-f" in cmd
        assert "concat" in cmd

    def test_empty_list(self):
        """Empty segment list returns False."""
        result = concatenate_segments([], Path("out.mp4"))

        assert result is False
