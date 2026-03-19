"""Tests for highlights.py module (mocked subprocess + cv2 + BirdDetector).

@author Claude Opus 4.6 Anthropic
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from birdbird.highlights import (
    Segment,
    _binary_search_entry,
    _binary_search_exit,
    concatenate_segments,
    detect_hardware_encoder,
    extract_segment,
    find_bird_segments,
    generate_highlights,
    get_video_duration,
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
                    Path("test.avi"),
                    detector,
                    buffer_before=1.0,
                    buffer_after=1.0,
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


# ---------------------------------------------------------------------------
# TestGenerateHighlights
# ---------------------------------------------------------------------------


def _make_segment(clip_path: Path, start: float = 0.0, end: float = 5.0) -> Segment:
    return Segment(clip_path=clip_path, start_time=start, end_time=end)


class TestGenerateHighlights:
    """Tests for generate_highlights().

    @author Claude Sonnet 4.6 Anthropic
    """

    def _common_patches(self, find_segments_return=None, extract_return=True, concat_return=True):
        """Return a dict of patch targets and their return values for the main happy path."""
        seg = MagicMock()  # a dummy Segment
        return {
            "birdbird.highlights.detect_hardware_encoder": None,
            "birdbird.highlights.load_detections": FileNotFoundError,
            "birdbird.highlights.find_bird_segments": [seg] if find_segments_return is None else find_segments_return,
            "birdbird.highlights.extract_segment": extract_return,
            "birdbird.highlights.concatenate_segments": concat_return,
            "birdbird.highlights.get_video_duration": 10.0,
            "birdbird.highlights.tqdm": None,  # replaced with passthrough
        }

    def _run(self, tmp_path, *, clips=1, find_return=None, extract_return=True, concat_return=True, detections=None):
        """Create AVI files in tmp_path and call generate_highlights() with all external deps mocked."""
        input_dir = tmp_path / "clips"
        input_dir.mkdir()
        for i in range(clips):
            (input_dir / f"clip_{i:02d}.avi").write_bytes(b"fake")

        output_path = tmp_path / "highlights.mp4"

        # Build a mock BirdbirdPaths
        mock_paths = MagicMock()
        mock_paths.detections_json = tmp_path / "detections.json"

        dummy_segment = _make_segment(input_dir / "clip_00.avi")
        find_return = [dummy_segment] if find_return is None else find_return

        def fake_tqdm(iterable, **_kwargs):
            return iterable

        with patch("birdbird.highlights.detect_hardware_encoder", return_value=None):
            with patch("birdbird.highlights.tqdm", side_effect=fake_tqdm):
                with patch("birdbird.highlights.find_bird_segments", return_value=find_return):
                    with patch("birdbird.highlights.extract_segment", return_value=extract_return):
                        with patch("birdbird.highlights.concatenate_segments", return_value=concat_return):
                            with patch("birdbird.highlights.get_video_duration", return_value=10.0):
                                with patch("birdbird.highlights.load_detections") as mock_load:
                                    if detections is not None:
                                        mock_load.return_value = detections
                                    else:
                                        mock_load.side_effect = FileNotFoundError
                                    return generate_highlights(
                                        input_dir=input_dir,
                                        output_path=output_path,
                                        paths=mock_paths,
                                    )

    def test_raises_when_no_avi_clips(self, tmp_path):
        """Raises ValueError when input_dir contains no .avi files."""
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()
        mock_paths = MagicMock()

        with pytest.raises(ValueError, match="No .avi clips found"):
            generate_highlights(input_dir=empty_dir, output_path=tmp_path / "out.mp4", paths=mock_paths)

    def test_raises_when_no_bird_segments(self, tmp_path):
        """Raises ValueError when find_bird_segments returns empty for all clips."""
        with pytest.raises(ValueError, match="No bird segments found"):
            self._run(tmp_path, find_return=[])

    def test_raises_when_concatenation_fails(self, tmp_path):
        """Raises RuntimeError when concatenate_segments returns False."""
        with pytest.raises(RuntimeError, match="Failed to concatenate"):
            self._run(tmp_path, concat_return=False)

    def test_returns_highlights_stats(self, tmp_path):
        """Returns HighlightsStats with populated fields."""
        stats = self._run(tmp_path, clips=3)

        assert stats.clip_count == 3
        assert stats.segment_count == 3  # one segment per clip (mocked)
        assert stats.final_duration == 10.0  # from get_video_duration mock
        assert stats.bird_clips_duration >= 0.0

    def test_uses_cached_detections_known_first_bird(self, tmp_path):
        """Passes known_first_bird from cached detections to find_bird_segments."""
        input_dir = tmp_path / "clips"
        input_dir.mkdir()
        (input_dir / "clip_00.avi").write_bytes(b"fake")

        output_path = tmp_path / "out.mp4"
        mock_paths = MagicMock()
        mock_paths.detections_json = tmp_path / "detections.json"

        cached = {"clip_00.avi": {"first_bird": 3.5}}
        dummy_segment = _make_segment(input_dir / "clip_00.avi")
        mock_find = MagicMock(return_value=[dummy_segment])

        def fake_tqdm(iterable, **_kwargs):
            return iterable

        with patch("birdbird.highlights.detect_hardware_encoder", return_value=None):
            with patch("birdbird.highlights.tqdm", side_effect=fake_tqdm):
                with patch("birdbird.highlights.find_bird_segments", mock_find):
                    with patch("birdbird.highlights.extract_segment", return_value=True):
                        with patch("birdbird.highlights.concatenate_segments", return_value=True):
                            with patch("birdbird.highlights.get_video_duration", return_value=10.0):
                                with patch("birdbird.highlights.load_detections", return_value=cached):
                                    generate_highlights(
                                        input_dir=input_dir,
                                        output_path=output_path,
                                        paths=mock_paths,
                                    )

        # Check that known_first_bird=3.5 was passed (positional arg, index 4)
        call_args = mock_find.call_args[0]
        assert call_args[4] == 3.5

    def test_falls_back_gracefully_when_detections_missing(self, tmp_path):
        """Continues without cache when detections.json is absent."""
        # Should not raise — FileNotFoundError from load_detections is swallowed
        stats = self._run(tmp_path, detections=None)
        assert stats is not None

    def test_optimize_web_passed_through(self, tmp_path):
        """optimize_web flag is forwarded to extract_segment."""
        input_dir = tmp_path / "clips"
        input_dir.mkdir()
        (input_dir / "clip_00.avi").write_bytes(b"fake")
        output_path = tmp_path / "out.mp4"
        mock_paths = MagicMock()
        mock_paths.detections_json = tmp_path / "detections.json"

        dummy_segment = _make_segment(input_dir / "clip_00.avi")
        mock_extract = MagicMock(return_value=True)

        def fake_tqdm(iterable, **_kwargs):
            return iterable

        with patch("birdbird.highlights.detect_hardware_encoder", return_value=None):
            with patch("birdbird.highlights.tqdm", side_effect=fake_tqdm):
                with patch("birdbird.highlights.find_bird_segments", return_value=[dummy_segment]):
                    with patch("birdbird.highlights.extract_segment", mock_extract):
                        with patch("birdbird.highlights.concatenate_segments", return_value=True):
                            with patch("birdbird.highlights.get_video_duration", return_value=10.0):
                                with patch("birdbird.highlights.load_detections", side_effect=FileNotFoundError):
                                    generate_highlights(
                                        input_dir=input_dir,
                                        output_path=output_path,
                                        paths=mock_paths,
                                        optimize_web=True,
                                    )

        # optimize_web is the 4th positional arg to extract_segment
        call_args = mock_extract.call_args[0]
        assert call_args[3] is True

    def test_segment_count_matches_extracted_files(self, tmp_path):
        """segment_count in stats equals the number of successfully extracted segments."""
        input_dir = tmp_path / "clips"
        input_dir.mkdir()
        (input_dir / "clip_00.avi").write_bytes(b"fake")
        output_path = tmp_path / "out.mp4"
        mock_paths = MagicMock()
        mock_paths.detections_json = tmp_path / "detections.json"

        # Three segments from the single clip
        segments = [
            _make_segment(input_dir / "clip_00.avi", 0.0, 3.0),
            _make_segment(input_dir / "clip_00.avi", 5.0, 8.0),
            _make_segment(input_dir / "clip_00.avi", 10.0, 13.0),
        ]

        def fake_tqdm(iterable, **_kwargs):
            return iterable

        with patch("birdbird.highlights.detect_hardware_encoder", return_value=None):
            with patch("birdbird.highlights.tqdm", side_effect=fake_tqdm):
                with patch("birdbird.highlights.find_bird_segments", return_value=segments):
                    with patch("birdbird.highlights.extract_segment", return_value=True):
                        with patch("birdbird.highlights.concatenate_segments", return_value=True):
                            with patch("birdbird.highlights.get_video_duration", return_value=10.0):
                                with patch("birdbird.highlights.load_detections", side_effect=FileNotFoundError):
                                    stats = generate_highlights(
                                        input_dir=input_dir,
                                        output_path=output_path,
                                        paths=mock_paths,
                                    )

        assert stats.segment_count == 3
