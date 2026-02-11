"""Tests for species.py module (mocked BioCLIP + torch).

@author Claude Sonnet 4.5 Anthropic
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from birdbird.species import LocalProcessor, Detection


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
        return [
            {"classification": species, "score": score}
            for species, score in species_scores
        ]
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

    def test_cuda_available(self, tmp_path, mock_torch_and_bioclip, mock_bioclip_predictions):
        """Uses CUDA device when available."""
        mock_torch, mock_bioclip, mock_classifier = mock_torch_and_bioclip
        labels = ["Blue Tit", "Robin"]

        # Need at least one frame to trigger import
        frame_path = tmp_path / "frame_0000.jpg"
        frame_path.touch()
        frames = [(frame_path, 1.0)]

        mock_classifier.predict.return_value = mock_bioclip_predictions([("Blue Tit", 0.9)])

        with patch("birdbird.species.tqdm", side_effect=lambda x, **kwargs: x):
            processor = LocalProcessor(labels=labels, min_confidence=0.5)
            processor.process(frames)

            # Verify CUDA was checked and classifier initialized with cuda device
            mock_torch.cuda.is_available.assert_called_once()
            mock_bioclip.CustomLabelsClassifier.assert_called_once_with(labels, device="cuda")

    def test_cuda_not_available_falls_back_to_cpu(self, tmp_path, mock_torch_and_bioclip, mock_bioclip_predictions):
        """Falls back to CPU when CUDA not available."""
        mock_torch, mock_bioclip, mock_classifier = mock_torch_and_bioclip
        mock_torch.cuda.is_available.return_value = False
        labels = ["Blue Tit", "Robin"]

        # Need at least one frame to trigger import
        frame_path = tmp_path / "frame_0000.jpg"
        frame_path.touch()
        frames = [(frame_path, 1.0)]

        mock_classifier.predict.return_value = mock_bioclip_predictions([("Robin", 0.8)])

        with patch("birdbird.species.tqdm", side_effect=lambda x, **kwargs: x):
            processor = LocalProcessor(labels=labels, min_confidence=0.5)
            processor.process(frames)

            mock_bioclip.CustomLabelsClassifier.assert_called_once_with(labels, device="cpu")

    def test_empty_frames_returns_empty_list(self):
        """Empty frames list returns empty detections."""
        labels = ["Blue Tit", "Robin"]
        processor = LocalProcessor(labels=labels, min_confidence=0.5)

        result = processor.process([])

        assert result == []

    def test_detection_above_threshold(self, tmp_path, mock_bioclip_predictions, mock_torch_and_bioclip):
        """Detection above confidence threshold is included."""
        _, _, mock_classifier = mock_torch_and_bioclip
        labels = ["Blue Tit", "Robin", "Blackbird"]

        frame_path = tmp_path / "frame_0000.jpg"
        frame_path.touch()
        frames = [(frame_path, 5.0)]

        # BioCLIP returns predictions sorted by score
        predictions = mock_bioclip_predictions([
            ("Blue Tit", 0.85),
            ("Robin", 0.12),
            ("Blackbird", 0.03),
        ])
        mock_classifier.predict.return_value = predictions

        with patch("birdbird.species.tqdm", side_effect=lambda x, **kwargs: x):
            processor = LocalProcessor(labels=labels, min_confidence=0.5)
            detections = processor.process(frames)

        assert len(detections) == 1
        assert detections[0].timestamp_s == 5.0
        assert detections[0].species == "Blue Tit"
        assert detections[0].confidence == 0.85
        assert len(detections[0].runners_up) == 2
        assert detections[0].runners_up[0] == {"species": "Robin", "confidence": 0.12}

    def test_detection_below_threshold_excluded(self, tmp_path, mock_bioclip_predictions, mock_torch_and_bioclip):
        """Detection below confidence threshold is excluded."""
        _, _, mock_classifier = mock_torch_and_bioclip
        labels = ["Blue Tit", "Robin"]

        frame_path = tmp_path / "frame_0000.jpg"
        frame_path.touch()
        frames = [(frame_path, 3.0)]

        # All predictions below 0.5 threshold
        predictions = mock_bioclip_predictions([
            ("Robin", 0.45),
            ("Blue Tit", 0.35),
        ])
        mock_classifier.predict.return_value = predictions

        with patch("birdbird.species.tqdm", side_effect=lambda x, **kwargs: x):
            processor = LocalProcessor(labels=labels, min_confidence=0.5)
            detections = processor.process(frames)

        assert len(detections) == 0

    def test_multiple_frames_processed(self, tmp_path, mock_bioclip_predictions, mock_torch_and_bioclip):
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

        with patch("birdbird.species.tqdm", side_effect=lambda x, **kwargs: x):
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

    def test_runners_up_limited_to_three(self, tmp_path, mock_bioclip_predictions, mock_torch_and_bioclip):
        """Runners-up list is limited to top 3."""
        _, _, mock_classifier = mock_torch_and_bioclip
        labels = ["Blue Tit", "Robin", "Blackbird", "Great Tit", "House Sparrow"]

        frame_path = tmp_path / "frame_0000.jpg"
        frame_path.touch()
        frames = [(frame_path, 1.0)]

        predictions = mock_bioclip_predictions([
            ("Blue Tit", 0.85),
            ("Robin", 0.10),
            ("Blackbird", 0.03),
            ("Great Tit", 0.01),
            ("House Sparrow", 0.01),
        ])
        mock_classifier.predict.return_value = predictions

        with patch("birdbird.species.tqdm", side_effect=lambda x, **kwargs: x):
            processor = LocalProcessor(labels=labels, min_confidence=0.5)
            detections = processor.process(frames)

        assert len(detections) == 1
        # Should only have 3 runners-up (Robin, Blackbird, Great Tit)
        assert len(detections[0].runners_up) == 3
        assert detections[0].runners_up[0]["species"] == "Robin"
        assert detections[0].runners_up[1]["species"] == "Blackbird"
        assert detections[0].runners_up[2]["species"] == "Great Tit"

    def test_confidence_rounded_to_four_decimals(self, tmp_path, mock_bioclip_predictions, mock_torch_and_bioclip):
        """Confidence scores are rounded to 4 decimal places."""
        _, _, mock_classifier = mock_torch_and_bioclip
        labels = ["Blue Tit"]

        frame_path = tmp_path / "frame_0000.jpg"
        frame_path.touch()
        frames = [(frame_path, 1.0)]

        predictions = mock_bioclip_predictions([
            ("Blue Tit", 0.876543210),
        ])
        mock_classifier.predict.return_value = predictions

        with patch("birdbird.species.tqdm", side_effect=lambda x, **kwargs: x):
            processor = LocalProcessor(labels=labels, min_confidence=0.5)
            detections = processor.process(frames)

        assert detections[0].confidence == 0.8765

    def test_progress_callback_called(self, tmp_path, mock_torch_and_bioclip, mock_bioclip_predictions):
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

        with patch("birdbird.species.tqdm", side_effect=lambda x, **kwargs: x):
            processor.process(frames, progress_callback=callback)

        # Should get two callback calls
        assert callback.call_count == 2
        # First call: loading message
        assert "Loading BioCLIP" in callback.call_args_list[0][0][0]
        assert "cuda" in callback.call_args_list[0][0][0].lower()
        # Second call: processing message
        assert "Processing" in callback.call_args_list[1][0][0]
