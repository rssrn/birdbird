"""Tests for paths.py module.

@author Claude Sonnet 4.5 Anthropic
"""

import json
from pathlib import Path

import pytest

from birdbird.paths import (
    BirdbirdPaths,
    get_asset_frame_paths,
    load_detections,
)


class TestBirdbirdPaths:
    """Tests for BirdbirdPaths class."""

    def test_from_input_dir_basic(self, tmp_input_dir):
        """Test basic path construction from input directory."""
        paths = BirdbirdPaths.from_input_dir(tmp_input_dir)

        assert paths.input_dir == tmp_input_dir
        assert paths.birdbird_dir == tmp_input_dir / "birdbird"
        assert paths.working_dir == tmp_input_dir / "birdbird" / "working"
        assert paths.assets_dir == tmp_input_dir / "birdbird" / "assets"

    def test_from_input_dir_filter_paths(self, tmp_input_dir):
        """Test filter-related paths."""
        paths = BirdbirdPaths.from_input_dir(tmp_input_dir)

        assert paths.filter_dir == tmp_input_dir / "birdbird" / "working" / "filter"
        assert paths.clips_dir == tmp_input_dir / "birdbird" / "working" / "filter" / "clips"
        assert paths.detections_json == tmp_input_dir / "birdbird" / "working" / "filter" / "detections.json"

    def test_from_input_dir_frames_paths(self, tmp_input_dir):
        """Test frames-related paths."""
        paths = BirdbirdPaths.from_input_dir(tmp_input_dir)

        assert paths.frames_working_dir == tmp_input_dir / "birdbird" / "working" / "frames"
        assert paths.frames_candidates_dir == tmp_input_dir / "birdbird" / "working" / "frames" / "candidates"
        assert paths.frame_scores_json == tmp_input_dir / "birdbird" / "working" / "frames" / "frame_scores.json"

    def test_from_input_dir_assets_paths(self, tmp_input_dir):
        """Test assets-related paths."""
        paths = BirdbirdPaths.from_input_dir(tmp_input_dir)

        assert paths.highlights_mp4 == tmp_input_dir / "birdbird" / "assets" / "highlights.mp4"
        assert paths.metadata_json == tmp_input_dir / "birdbird" / "assets" / "metadata.json"
        assert paths.songs_json == tmp_input_dir / "birdbird" / "assets" / "songs.json"
        assert paths.species_json == tmp_input_dir / "birdbird" / "assets" / "species.json"
        assert paths.best_clips_json == tmp_input_dir / "birdbird" / "assets" / "best_clips.json"
        assert paths.song_clips_dir == tmp_input_dir / "birdbird" / "assets" / "song_clips"

    def test_from_input_dir_with_string(self, tmp_input_dir):
        """Test path construction from string path."""
        paths = BirdbirdPaths.from_input_dir(str(tmp_input_dir))

        assert paths.input_dir == tmp_input_dir
        assert isinstance(paths.input_dir, Path)

    def test_ensure_working_dirs(self, tmp_input_dir):
        """Test working directory creation."""
        paths = BirdbirdPaths.from_input_dir(tmp_input_dir)

        # Directories should not exist yet
        assert not paths.clips_dir.exists()
        assert not paths.frames_candidates_dir.exists()

        # Create directories
        paths.ensure_working_dirs()

        # Directories should now exist
        assert paths.clips_dir.exists()
        assert paths.clips_dir.is_dir()
        assert paths.frames_candidates_dir.exists()
        assert paths.frames_candidates_dir.is_dir()

        # Should be idempotent (no error on second call)
        paths.ensure_working_dirs()
        assert paths.clips_dir.exists()

    def test_ensure_assets_dirs(self, tmp_input_dir):
        """Test assets directory creation."""
        paths = BirdbirdPaths.from_input_dir(tmp_input_dir)

        # Directories should not exist yet
        assert not paths.assets_dir.exists()
        assert not paths.song_clips_dir.exists()

        # Create directories
        paths.ensure_assets_dirs()

        # Directories should now exist
        assert paths.assets_dir.exists()
        assert paths.assets_dir.is_dir()
        assert paths.song_clips_dir.exists()
        assert paths.song_clips_dir.is_dir()

        # Should be idempotent
        paths.ensure_assets_dirs()
        assert paths.assets_dir.exists()


class TestGetAssetFramePaths:
    """Tests for get_asset_frame_paths()."""

    def test_default_top_n(self, tmp_path):
        """Test default top_n=3."""
        assets_dir = tmp_path / "assets"
        paths = get_asset_frame_paths(assets_dir)

        assert len(paths) == 3
        assert paths[0] == assets_dir / "frame_01.jpg"
        assert paths[1] == assets_dir / "frame_02.jpg"
        assert paths[2] == assets_dir / "frame_03.jpg"

    def test_custom_top_n(self, tmp_path):
        """Test custom top_n values."""
        assets_dir = tmp_path / "assets"

        paths_5 = get_asset_frame_paths(assets_dir, top_n=5)
        assert len(paths_5) == 5
        assert paths_5[4] == assets_dir / "frame_05.jpg"

        paths_1 = get_asset_frame_paths(assets_dir, top_n=1)
        assert len(paths_1) == 1
        assert paths_1[0] == assets_dir / "frame_01.jpg"

    def test_numbering_format(self, tmp_path):
        """Test correct zero-padded numbering."""
        assets_dir = tmp_path / "assets"
        paths = get_asset_frame_paths(assets_dir, top_n=10)

        assert paths[0].name == "frame_01.jpg"
        assert paths[8].name == "frame_09.jpg"
        assert paths[9].name == "frame_10.jpg"


class TestLoadDetections:
    """Tests for load_detections()."""

    def test_load_valid_detections(self, tmp_path):
        """Test loading valid detections.json."""
        detections_path = tmp_path / "detections.json"
        test_data = {
            "1408301500.avi": {
                "first_bird": 1.5,
                "confidence": 0.92,
            },
            "1508301600.avi": {
                "first_bird": 0.5,
                "confidence": 0.87,
            },
        }
        detections_path.write_text(json.dumps(test_data))

        result = load_detections(detections_path)
        assert result == test_data
        assert len(result) == 2
        assert result["1408301500.avi"]["confidence"] == 0.92

    def test_load_empty_detections(self, tmp_path):
        """Test loading empty detections file."""
        detections_path = tmp_path / "detections.json"
        detections_path.write_text("{}")

        result = load_detections(detections_path)
        assert result == {}

    def test_load_missing_file(self, tmp_path):
        """Test loading non-existent detections file."""
        detections_path = tmp_path / "missing.json"

        with pytest.raises(FileNotFoundError) as exc_info:
            load_detections(detections_path)

        assert "Detections file not found" in str(exc_info.value)
        assert "birdbird filter" in str(exc_info.value)

    def test_load_detections_with_path_object(self, tmp_path):
        """Test loading detections with Path object."""
        detections_path = tmp_path / "detections.json"
        test_data = {"test.avi": {"first_bird": 1.0, "confidence": 0.8}}
        detections_path.write_text(json.dumps(test_data))

        result = load_detections(detections_path)
        assert result == test_data
