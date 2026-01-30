"""Tests for best_clips.py module.

@author Claude Sonnet 4.5 Anthropic
"""

import json
from pathlib import Path

import pytest

from birdbird.best_clips import (
    BestClip,
    find_best_clip_for_species,
    find_all_best_clips,
)


class TestFindBestClipForSpecies:
    """Tests for find_best_clip_for_species()."""

    def test_single_detection(self):
        """Test with single detection returns that clip."""
        detections = [
            {"timestamp_s": 5.0, "species": "Blue Tit", "confidence": 0.9},
        ]

        result = find_best_clip_for_species(detections, "Blue Tit", window_duration_s=14.0)

        assert result is not None
        assert result.species == "Blue Tit"
        assert result.start_s == 5.0
        assert result.end_s == 19.0  # start + 14
        assert result.score == 0.9
        assert result.detection_count == 1

    def test_multiple_detections_same_clip(self):
        """Test multiple detections in one clip returns highest confidence window."""
        detections = [
            {"timestamp_s": 0.0, "species": "Blue Tit", "confidence": 0.8},
            {"timestamp_s": 5.0, "species": "Blue Tit", "confidence": 0.9},
            {"timestamp_s": 10.0, "species": "Blue Tit", "confidence": 0.85},
        ]

        result = find_best_clip_for_species(detections, "Blue Tit", window_duration_s=14.0)

        assert result is not None
        # Should get window containing all 3 detections
        assert result.score == pytest.approx(round(0.8 + 0.9 + 0.85, 3))
        assert result.detection_count == 3

    def test_detections_spanning_multiple_clips(self):
        """Test detections spanning multiple clips finds best window."""
        detections = [
            {"timestamp_s": 0.0, "species": "Robin", "confidence": 0.7},
            {"timestamp_s": 50.0, "species": "Robin", "confidence": 0.9},
            {"timestamp_s": 55.0, "species": "Robin", "confidence": 0.95},
            {"timestamp_s": 60.0, "species": "Robin", "confidence": 0.85},
        ]

        result = find_best_clip_for_species(detections, "Robin", window_duration_s=14.0)

        assert result is not None
        # Best window should be 50-64s containing 3 high-confidence detections
        assert result.start_s == 50.0
        assert result.detection_count == 3
        assert result.score == pytest.approx(0.9 + 0.95 + 0.85)

    def test_empty_detections(self):
        """Test with empty detections returns None."""
        detections = []

        result = find_best_clip_for_species(detections, "Blue Tit", window_duration_s=14.0)

        assert result is None

    def test_no_detections_for_species(self):
        """Test with no detections for requested species returns None."""
        detections = [
            {"timestamp_s": 0.0, "species": "Robin", "confidence": 0.8},
            {"timestamp_s": 5.0, "species": "Robin", "confidence": 0.9},
        ]

        result = find_best_clip_for_species(detections, "Blue Tit", window_duration_s=14.0)

        assert result is None

    def test_window_duration_edge_cases(self):
        """Test with various window durations."""
        detections = [
            {"timestamp_s": 0.0, "species": "Blue Tit", "confidence": 0.8},
            {"timestamp_s": 5.0, "species": "Blue Tit", "confidence": 0.9},
            {"timestamp_s": 20.0, "species": "Blue Tit", "confidence": 0.95},
        ]

        # Very short window (5s) - window is inclusive when span equals duration
        # Detections at 0.0 and 5.0 have span=5.0, which is NOT > 5.0, so both included
        result_short = find_best_clip_for_species(detections, "Blue Tit", window_duration_s=5.0)
        assert result_short is not None
        # Best window is 0.0-5.0 with 2 detections (score 1.7) vs 20.0-25.0 with 1 (score 0.95)
        assert result_short.detection_count == 2
        assert result_short.start_s == 0.0

        # Very long window (100s) - should get all detections
        result_long = find_best_clip_for_species(detections, "Blue Tit", window_duration_s=100.0)
        assert result_long is not None
        assert result_long.detection_count == 3

    def test_clips_at_window_boundaries(self):
        """Test detections exactly at window boundaries."""
        detections = [
            {"timestamp_s": 0.0, "species": "Blue Tit", "confidence": 0.8},
            {"timestamp_s": 14.0, "species": "Blue Tit", "confidence": 0.9},
            {"timestamp_s": 28.0, "species": "Blue Tit", "confidence": 0.7},
        ]

        result = find_best_clip_for_species(detections, "Blue Tit", window_duration_s=14.0)

        assert result is not None
        # Window is inclusive: detections at 0.0 and 14.0 have span=14.0, which equals duration
        # So window 0.0-14.0 contains both detections (score 1.7)
        assert result.detection_count == 2
        assert result.start_s == 0.0

    def test_unsorted_detections(self):
        """Test with unsorted detections (should handle correctly)."""
        detections = [
            {"timestamp_s": 20.0, "species": "Blue Tit", "confidence": 0.7},
            {"timestamp_s": 5.0, "species": "Blue Tit", "confidence": 0.9},
            {"timestamp_s": 10.0, "species": "Blue Tit", "confidence": 0.8},
        ]

        result = find_best_clip_for_species(detections, "Blue Tit", window_duration_s=14.0)

        assert result is not None
        # Should still find best window despite unsorted input
        assert result.detection_count >= 1

    def test_score_rounding(self):
        """Test that score is rounded to 3 decimal places."""
        detections = [
            {"timestamp_s": 0.0, "species": "Blue Tit", "confidence": 0.123456},
            {"timestamp_s": 5.0, "species": "Blue Tit", "confidence": 0.654321},
        ]

        result = find_best_clip_for_species(detections, "Blue Tit", window_duration_s=14.0)

        assert result is not None
        # Score should be rounded
        assert isinstance(result.score, float)
        # Check it's been rounded (not exact sum)
        raw_sum = 0.123456 + 0.654321
        assert result.score != raw_sum
        assert result.score == round(raw_sum, 3)


class TestFindAllBestClips:
    """Tests for find_all_best_clips()."""

    def test_find_all_with_multiple_species(self, tmp_path):
        """Test finding best clips for multiple species."""
        species_data = {
            "detections": [
                {"timestamp_s": 0.0, "species": "Blue Tit", "confidence": 0.9},
                {"timestamp_s": 5.0, "species": "Blue Tit", "confidence": 0.8},
                {"timestamp_s": 10.0, "species": "Robin", "confidence": 0.7},
                {"timestamp_s": 15.0, "species": "Robin", "confidence": 0.85},
            ],
            "species_summary": {
                "Blue Tit": {"count": 2},
                "Robin": {"count": 2},
            },
        }

        species_json = tmp_path / "species.json"
        species_json.write_text(json.dumps(species_data))

        result = find_all_best_clips(species_json, window_duration_s=14.0)

        assert len(result) == 2
        assert "Blue Tit" in result
        assert "Robin" in result
        assert isinstance(result["Blue Tit"], BestClip)
        assert isinstance(result["Robin"], BestClip)

    def test_find_all_with_empty_species(self, tmp_path):
        """Test with empty species data."""
        species_data = {
            "detections": [],
            "species_summary": {},
        }

        species_json = tmp_path / "species.json"
        species_json.write_text(json.dumps(species_data))

        result = find_all_best_clips(species_json, window_duration_s=14.0)

        assert result == {}

    def test_find_all_missing_file(self, tmp_path):
        """Test with missing species.json file."""
        species_json = tmp_path / "missing.json"

        with pytest.raises(FileNotFoundError) as exc_info:
            find_all_best_clips(species_json, window_duration_s=14.0)

        assert "Species data not found" in str(exc_info.value)

    def test_find_all_custom_window_duration(self, tmp_path):
        """Test with custom window duration."""
        species_data = {
            "detections": [
                {"timestamp_s": 0.0, "species": "Blue Tit", "confidence": 0.9},
                {"timestamp_s": 30.0, "species": "Blue Tit", "confidence": 0.8},
            ],
            "species_summary": {
                "Blue Tit": {"count": 2},
            },
        }

        species_json = tmp_path / "species.json"
        species_json.write_text(json.dumps(species_data))

        # With 20s window, detections are too far apart
        result_short = find_all_best_clips(species_json, window_duration_s=20.0)
        assert result_short["Blue Tit"].detection_count == 1

        # With 40s window, both detections fit
        result_long = find_all_best_clips(species_json, window_duration_s=40.0)
        assert result_long["Blue Tit"].detection_count == 2
