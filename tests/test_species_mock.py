"""Tests for species.py module (mocked BioCLIP + torch).

@author Claude Sonnet 4.5 Anthropic
"""

import json
import sys
from unittest.mock import MagicMock, patch

import pytest

from birdbird.species import (
    Detection,
    LocalProcessor,
    RemoteProcessor,
    SpeciesResults,
    aggregate_species_summary,
    check_remote_connection,
    identify_species,
    parse_labels_file,
    save_species_results,
)


@pytest.fixture
def mock_bioclip_predictions():
    """Factory for creating mock BioCLIP prediction results."""

    def _make_predictions(species_scores):
        """
        Args:
            species_scores: List of (species, score) tuples

        Returns:
            List of dicts with 'classification' and 'score' keys
        """
        return [{"classification": species, "score": score} for species, score in species_scores]

    return _make_predictions


@pytest.fixture
def mock_torch_and_bioclip():
    """Mock torch and bioclip imports for LocalProcessor."""
    mock_torch = MagicMock()
    mock_bioclip = MagicMock()

    # Setup torch mock
    mock_torch.cuda.is_available.return_value = True

    # Setup bioclip mock
    mock_classifier = MagicMock()
    mock_bioclip.CustomLabelsClassifier.return_value = mock_classifier

    # Inject into sys.modules so imports work
    with patch.dict(sys.modules, {"torch": mock_torch, "bioclip": mock_bioclip}):
        yield mock_torch, mock_bioclip, mock_classifier


class TestLocalProcessor:
    """Tests for LocalProcessor class."""

    def test_cuda_available(self, tmp_path, mock_torch_and_bioclip, mock_bioclip_predictions, mocker):
        """Uses CUDA device when available."""
        mock_torch, mock_bioclip, mock_classifier = mock_torch_and_bioclip
        labels = ["Blue Tit", "Robin"]

        # Need at least one frame to trigger import
        frame_path = tmp_path / "frame_0000.jpg"
        frame_path.touch()
        frames = [(frame_path, 1.0)]

        mock_classifier.predict.return_value = mock_bioclip_predictions([("Blue Tit", 0.9)])

        mocker.patch("birdbird.species.tqdm", side_effect=lambda x, **kwargs: x)
        processor = LocalProcessor(labels=labels, min_confidence=0.5)
        processor.process(frames)

        # Verify CUDA was checked and classifier initialized with cuda device
        mock_torch.cuda.is_available.assert_called_once()
        mock_bioclip.CustomLabelsClassifier.assert_called_once_with(labels, device="cuda")

    def test_cuda_not_available_falls_back_to_cpu(
        self, tmp_path, mock_torch_and_bioclip, mock_bioclip_predictions, mocker
    ):
        """Falls back to CPU when CUDA not available."""
        mock_torch, mock_bioclip, mock_classifier = mock_torch_and_bioclip
        mock_torch.cuda.is_available.return_value = False
        labels = ["Blue Tit", "Robin"]

        # Need at least one frame to trigger import
        frame_path = tmp_path / "frame_0000.jpg"
        frame_path.touch()
        frames = [(frame_path, 1.0)]

        mock_classifier.predict.return_value = mock_bioclip_predictions([("Robin", 0.8)])

        mocker.patch("birdbird.species.tqdm", side_effect=lambda x, **kwargs: x)
        processor = LocalProcessor(labels=labels, min_confidence=0.5)
        processor.process(frames)

        mock_bioclip.CustomLabelsClassifier.assert_called_once_with(labels, device="cpu")

    def test_empty_frames_returns_empty_list(self):
        """Empty frames list returns empty detections."""
        labels = ["Blue Tit", "Robin"]
        processor = LocalProcessor(labels=labels, min_confidence=0.5)

        result = processor.process([])

        assert result == []

    def test_detection_above_threshold(self, tmp_path, mock_bioclip_predictions, mock_torch_and_bioclip, mocker):
        """Detection above confidence threshold is included."""
        _, _, mock_classifier = mock_torch_and_bioclip
        labels = ["Blue Tit", "Robin", "Blackbird"]

        frame_path = tmp_path / "frame_0000.jpg"
        frame_path.touch()
        frames = [(frame_path, 5.0)]

        # BioCLIP returns predictions sorted by score
        predictions = mock_bioclip_predictions(
            [
                ("Blue Tit", 0.85),
                ("Robin", 0.12),
                ("Blackbird", 0.03),
            ]
        )
        mock_classifier.predict.return_value = predictions

        mocker.patch("birdbird.species.tqdm", side_effect=lambda x, **kwargs: x)
        processor = LocalProcessor(labels=labels, min_confidence=0.5)
        detections = processor.process(frames)

        assert len(detections) == 1
        assert detections[0].timestamp_s == 5.0
        assert detections[0].species == "Blue Tit"
        assert detections[0].confidence == 0.85
        assert len(detections[0].runners_up) == 2
        assert detections[0].runners_up[0] == {"species": "Robin", "confidence": 0.12}

    def test_detection_below_threshold_excluded(
        self, tmp_path, mock_bioclip_predictions, mock_torch_and_bioclip, mocker
    ):
        """Detection below confidence threshold is excluded."""
        _, _, mock_classifier = mock_torch_and_bioclip
        labels = ["Blue Tit", "Robin"]

        frame_path = tmp_path / "frame_0000.jpg"
        frame_path.touch()
        frames = [(frame_path, 3.0)]

        # All predictions below 0.5 threshold
        predictions = mock_bioclip_predictions(
            [
                ("Robin", 0.45),
                ("Blue Tit", 0.35),
            ]
        )
        mock_classifier.predict.return_value = predictions

        mocker.patch("birdbird.species.tqdm", side_effect=lambda x, **kwargs: x)
        processor = LocalProcessor(labels=labels, min_confidence=0.5)
        detections = processor.process(frames)

        assert len(detections) == 0

    def test_multiple_frames_processed(self, tmp_path, mock_bioclip_predictions, mock_torch_and_bioclip, mocker):
        """Multiple frames are processed and return correct detections."""
        _, _, mock_classifier = mock_torch_and_bioclip
        labels = ["Blue Tit", "Robin"]

        frame1 = tmp_path / "frame_0000.jpg"
        frame2 = tmp_path / "frame_0001.jpg"
        frame3 = tmp_path / "frame_0002.jpg"
        frame1.touch()
        frame2.touch()
        frame3.touch()

        frames = [
            (frame1, 1.0),
            (frame2, 2.0),
            (frame3, 3.0),
        ]

        # Different predictions for each frame
        mock_classifier.predict.side_effect = [
            mock_bioclip_predictions([("Blue Tit", 0.9), ("Robin", 0.1)]),
            mock_bioclip_predictions([("Robin", 0.3), ("Blue Tit", 0.2)]),  # Below threshold
            mock_bioclip_predictions([("Robin", 0.75), ("Blue Tit", 0.25)]),
        ]

        mocker.patch("birdbird.species.tqdm", side_effect=lambda x, **kwargs: x)
        processor = LocalProcessor(labels=labels, min_confidence=0.5)
        detections = processor.process(frames)

        # Should get 2 detections (frame 1 and 3, frame 2 below threshold)
        assert len(detections) == 2
        assert detections[0].timestamp_s == 1.0
        assert detections[0].species == "Blue Tit"
        assert detections[0].confidence == 0.9

        assert detections[1].timestamp_s == 3.0
        assert detections[1].species == "Robin"
        assert detections[1].confidence == 0.75

    def test_runners_up_limited_to_three(self, tmp_path, mock_bioclip_predictions, mock_torch_and_bioclip, mocker):
        """Runners-up list is limited to top 3."""
        _, _, mock_classifier = mock_torch_and_bioclip
        labels = ["Blue Tit", "Robin", "Blackbird", "Great Tit", "House Sparrow"]

        frame_path = tmp_path / "frame_0000.jpg"
        frame_path.touch()
        frames = [(frame_path, 1.0)]

        predictions = mock_bioclip_predictions(
            [
                ("Blue Tit", 0.85),
                ("Robin", 0.10),
                ("Blackbird", 0.03),
                ("Great Tit", 0.01),
                ("House Sparrow", 0.01),
            ]
        )
        mock_classifier.predict.return_value = predictions

        mocker.patch("birdbird.species.tqdm", side_effect=lambda x, **kwargs: x)
        processor = LocalProcessor(labels=labels, min_confidence=0.5)
        detections = processor.process(frames)

        assert len(detections) == 1
        # Should only have 3 runners-up (Robin, Blackbird, Great Tit)
        assert len(detections[0].runners_up) == 3
        assert detections[0].runners_up[0]["species"] == "Robin"
        assert detections[0].runners_up[1]["species"] == "Blackbird"
        assert detections[0].runners_up[2]["species"] == "Great Tit"

    def test_confidence_rounded_to_four_decimals(
        self, tmp_path, mock_bioclip_predictions, mock_torch_and_bioclip, mocker
    ):
        """Confidence scores are rounded to 4 decimal places."""
        _, _, mock_classifier = mock_torch_and_bioclip
        labels = ["Blue Tit"]

        frame_path = tmp_path / "frame_0000.jpg"
        frame_path.touch()
        frames = [(frame_path, 1.0)]

        predictions = mock_bioclip_predictions(
            [
                ("Blue Tit", 0.876543210),
            ]
        )
        mock_classifier.predict.return_value = predictions

        mocker.patch("birdbird.species.tqdm", side_effect=lambda x, **kwargs: x)
        processor = LocalProcessor(labels=labels, min_confidence=0.5)
        detections = processor.process(frames)

        assert detections[0].confidence == 0.8765

    def test_progress_callback_called(self, tmp_path, mock_torch_and_bioclip, mock_bioclip_predictions, mocker):
        """Progress callback is invoked with status messages."""
        _, _, mock_classifier = mock_torch_and_bioclip
        labels = ["Blue Tit"]

        # Need at least one frame to trigger progress callbacks
        frame_path = tmp_path / "frame_0000.jpg"
        frame_path.touch()
        frames = [(frame_path, 1.0)]

        mock_classifier.predict.return_value = mock_bioclip_predictions([("Blue Tit", 0.9)])

        processor = LocalProcessor(labels=labels, min_confidence=0.5)

        callback = MagicMock()

        mocker.patch("birdbird.species.tqdm", side_effect=lambda x, **kwargs: x)
        processor.process(frames, progress_callback=callback)

        # Should get two callback calls
        assert callback.call_count == 2
        # First call: loading message
        assert "Loading BioCLIP" in callback.call_args_list[0][0][0]
        assert "cuda" in callback.call_args_list[0][0][0].lower()
        # Second call: processing message
        assert "Processing" in callback.call_args_list[1][0][0]


def _make_detection(species="Blue Tit", confidence=0.9, timestamp_s=1.0):
    return Detection(timestamp_s=timestamp_s, species=species, confidence=confidence, runners_up=[])


def _make_species_results(**kwargs):
    defaults = dict(
        generated_at="2026-01-14T12:00:00+00:00",
        processing_mode="remote",
        processing_time_s=5.0,
        highlights_duration_s=120.0,
        samples_per_minute=6.0,
        total_frames=12,
        species_summary={"Blue Tit": {"count": 2, "avg_confidence": 0.85}},
        detections=[_make_detection()],
    )
    defaults.update(kwargs)
    return SpeciesResults(**defaults)


class TestParseLabelsFile:
    """Tests for parse_labels_file().

    @author Claude Sonnet 4.6 Anthropic
    """

    def test_parses_normal_lines(self, tmp_path):
        """Returns list of stripped label strings."""
        labels_file = tmp_path / "labels.txt"
        labels_file.write_text("Blue Tit\nRobin\nGreat Tit\n")

        result = parse_labels_file(labels_file)

        assert result == ["Blue Tit", "Robin", "Great Tit"]

    def test_ignores_comment_lines(self, tmp_path):
        """Lines starting with # are excluded."""
        labels_file = tmp_path / "labels.txt"
        labels_file.write_text("# UK garden birds\nBlue Tit\n# common species\nRobin\n")

        result = parse_labels_file(labels_file)

        assert result == ["Blue Tit", "Robin"]

    def test_ignores_blank_lines(self, tmp_path):
        """Empty lines are excluded."""
        labels_file = tmp_path / "labels.txt"
        labels_file.write_text("Blue Tit\n\n\nRobin\n")

        result = parse_labels_file(labels_file)

        assert result == ["Blue Tit", "Robin"]

    def test_empty_file(self, tmp_path):
        """Empty file returns empty list."""
        labels_file = tmp_path / "labels.txt"
        labels_file.write_text("")

        result = parse_labels_file(labels_file)

        assert result == []


class TestCheckRemoteConnection:
    """Tests for check_remote_connection().

    @author Claude Sonnet 4.6 Anthropic
    """

    def _make_config(self):
        from birdbird.config import RemoteConfig

        return RemoteConfig(host="user@gpu.local", shell="bash", python_env="~/env", timeout=300)

    def test_success(self, mocker):
        """Returns (True, message) when SSH responds with 'ok'."""
        mocker.patch(
            "birdbird.species.subprocess.run",
            return_value=MagicMock(returncode=0, stdout="ok\n", stderr=""),
        )

        ok, msg = check_remote_connection(self._make_config())

        assert ok is True
        assert "successful" in msg.lower()

    def test_ssh_fails(self, mocker):
        """Returns (False, message) when SSH exits non-zero."""
        mocker.patch(
            "birdbird.species.subprocess.run",
            return_value=MagicMock(returncode=1, stdout="", stderr="Connection refused"),
        )

        ok, msg = check_remote_connection(self._make_config())

        assert ok is False
        assert "SSH failed" in msg

    def test_timeout(self, mocker):
        """Returns (False, message) when connection times out."""
        mocker.patch("birdbird.species.subprocess.run", side_effect=__import__("subprocess").TimeoutExpired("ssh", 10))

        ok, msg = check_remote_connection(self._make_config())

        assert ok is False
        assert "timed out" in msg.lower()


class TestAggregateSpeciesSummary:
    """Tests for aggregate_species_summary().

    @author Claude Sonnet 4.6 Anthropic
    """

    def test_groups_and_counts_detections(self):
        """Groups detections by species and counts them."""
        detections = [
            _make_detection("Blue Tit", 0.9),
            _make_detection("Blue Tit", 0.8),
            _make_detection("Robin", 0.7),
        ]

        result = aggregate_species_summary(detections)

        assert result["Blue Tit"]["count"] == 2
        assert result["Robin"]["count"] == 1

    def test_computes_average_confidence(self):
        """avg_confidence is the mean of all detection confidences for that species."""
        detections = [
            _make_detection("Blue Tit", 0.9),
            _make_detection("Blue Tit", 0.7),
        ]

        result = aggregate_species_summary(detections)

        assert result["Blue Tit"]["avg_confidence"] == pytest.approx(0.8, abs=0.001)

    def test_sorted_by_count_descending(self):
        """Species with more detections appear first."""
        detections = [
            _make_detection("Robin", 0.8),
            _make_detection("Blue Tit", 0.9),
            _make_detection("Blue Tit", 0.85),
            _make_detection("Blue Tit", 0.88),
        ]

        result = aggregate_species_summary(detections)

        assert list(result.keys())[0] == "Blue Tit"

    def test_empty_detections(self):
        """Empty input returns empty dict."""
        assert aggregate_species_summary([]) == {}


class TestSaveSpeciesResults:
    """Tests for save_species_results().

    @author Claude Sonnet 4.6 Anthropic
    """

    def test_json_structure(self, tmp_path):
        """Written JSON has all required top-level keys."""
        results = _make_species_results()
        output = tmp_path / "species.json"

        save_species_results(results, output)

        data = json.loads(output.read_text())
        required = {
            "generated_at",
            "processing_mode",
            "processing_time_s",
            "highlights_duration_s",
            "samples_per_minute",
            "total_frames",
            "species_summary",
            "detections",
        }
        assert required.issubset(data.keys())

    def test_detection_serialisation(self, tmp_path):
        """Each detection is serialised with timestamp_s, species, confidence, runners_up."""
        det = Detection(
            timestamp_s=3.5, species="Robin", confidence=0.82, runners_up=[{"species": "Sparrow", "confidence": 0.1}]
        )
        results = _make_species_results(detections=[det])
        output = tmp_path / "species.json"

        save_species_results(results, output)

        data = json.loads(output.read_text())
        assert len(data["detections"]) == 1
        d = data["detections"][0]
        assert d["timestamp_s"] == 3.5
        assert d["species"] == "Robin"
        assert d["confidence"] == pytest.approx(0.82)
        assert d["runners_up"] == [{"species": "Sparrow", "confidence": 0.1}]

    def test_species_summary_preserved(self, tmp_path):
        """species_summary dict is written verbatim."""
        summary = {"Blue Tit": {"count": 3, "avg_confidence": 0.87}}
        results = _make_species_results(species_summary=summary)
        output = tmp_path / "species.json"

        save_species_results(results, output)

        data = json.loads(output.read_text())
        assert data["species_summary"] == summary


class TestIdentifySpeciesValidation:
    """Tests for identify_species() mode validation (no real inference).

    @author Claude Sonnet 4.6 Anthropic
    """

    def test_raises_when_highlights_missing(self, tmp_path):
        """Raises ValueError when highlights video does not exist."""
        from birdbird.config import SpeciesConfig

        config = SpeciesConfig(processing_mode="remote", remote=None)
        with pytest.raises(ValueError, match="not found"):
            identify_species(tmp_path / "nonexistent.mp4", config=config)

    def test_remote_mode_raises_when_no_remote_config(self, tmp_path):
        """Raises ValueError when remote mode has no remote config block."""
        from birdbird.config import SpeciesConfig

        highlights = tmp_path / "highlights.mp4"
        highlights.write_bytes(b"fake")
        config = SpeciesConfig(processing_mode="remote", remote=None)

        with pytest.raises(ValueError, match="Remote processing mode requires"):
            identify_species(highlights, config=config)

    def test_cloud_mode_raises_not_implemented(self, tmp_path):
        """Raises ValueError for cloud processing mode (not yet implemented)."""
        from birdbird.config import SpeciesConfig

        highlights = tmp_path / "highlights.mp4"
        highlights.write_bytes(b"fake")
        config = SpeciesConfig(processing_mode="cloud", remote=None)

        with pytest.raises(ValueError, match="Cloud processing mode is not yet implemented"):
            identify_species(highlights, config=config)

    def test_local_mode_raises_when_deps_missing(self, tmp_path, mocker):
        """Raises ValueError when local mode deps (torch/bioclip) are not installed."""
        from birdbird.config import SpeciesConfig

        highlights = tmp_path / "highlights.mp4"
        highlights.write_bytes(b"fake")
        config = SpeciesConfig(processing_mode="local", remote=None)

        # Simulate missing dependencies
        mocker.patch.dict(sys.modules, {"torch": None, "bioclip": None})

        with pytest.raises(ValueError, match="Local processing requires"):
            identify_species(highlights, config=config)


class TestWindowsToWslPath:
    """Tests for RemoteProcessor._windows_to_wsl_path().

    @author Claude Opus 4.6 Anthropic
    """

    def _make_processor(self):
        from birdbird.config import RemoteConfig

        config = RemoteConfig(host="user@host", shell="wsl", python_env="~/env", timeout=300)
        return RemoteProcessor(config=config, labels=["Blue Tit"])

    def test_backslash_path(self):
        """Converts C:\\Users\\user\\AppData to /mnt/c/Users/user/AppData."""
        proc = self._make_processor()
        result = proc._windows_to_wsl_path("C:\\Users\\user\\AppData")
        assert result == "/mnt/c/Users/user/AppData"

    def test_forward_slash_path(self):
        """Converts C:/Users/user/AppData to /mnt/c/Users/user/AppData."""
        proc = self._make_processor()
        result = proc._windows_to_wsl_path("C:/Users/user/AppData")
        assert result == "/mnt/c/Users/user/AppData"

    def test_lowercase_drive_letter(self):
        """Drive letter is lowercased in WSL path."""
        proc = self._make_processor()
        result = proc._windows_to_wsl_path("D:\\Data\\temp")
        assert result == "/mnt/d/Data/temp"

    def test_no_drive_letter_passthrough(self):
        """Path without drive letter is returned as-is."""
        proc = self._make_processor()
        result = proc._windows_to_wsl_path("/already/wsl/path")
        assert result == "/already/wsl/path"

    def test_mixed_separators(self):
        """Handles mixed forward and backslash separators."""
        proc = self._make_processor()
        result = proc._windows_to_wsl_path("C:\\Users/user\\temp")
        assert result == "/mnt/c/Users/user/temp"
