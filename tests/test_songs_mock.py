"""Tests for songs.py module (mocked subprocess + birdnet_analyzer).

@author Claude Opus 4.6 Anthropic
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from birdbird.songs import (
    SongDetection,
    extract_audio,
    extract_audio_segment,
    extract_species_clips,
    analyze_songs,
    save_song_detections,
)


class TestExtractAudio:
    """Tests for extract_audio()."""

    def test_success(self):
        """Correct ffmpeg command, returns True on success."""
        with patch("birdbird.songs.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)

            result = extract_audio(Path("input.avi"), Path("output.wav"))

        assert result is True
        cmd = mock_run.call_args[0][0]
        assert cmd[0] == "ffmpeg"
        assert "-vn" in cmd
        assert "-acodec" in cmd
        assert "pcm_s16le" in cmd
        assert "-ar" in cmd
        assert "48000" in cmd

    def test_failure(self):
        """Returns False when ffmpeg fails."""
        with patch("birdbird.songs.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1)

            result = extract_audio(Path("input.avi"), Path("output.wav"))

        assert result is False


class TestExtractAudioSegment:
    """Tests for extract_audio_segment()."""

    def test_with_normalize(self):
        """Includes dynaudnorm filter when normalize=True."""
        with patch("birdbird.songs.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)

            extract_audio_segment(
                Path("input.avi"), Path("out.wav"),
                start_s=5.0, end_s=8.0, normalize=True,
            )

        cmd = mock_run.call_args[0][0]
        assert "-af" in cmd
        af_idx = cmd.index("-af")
        assert "dynaudnorm" in cmd[af_idx + 1]

    def test_without_normalize(self):
        """No audio filter when normalize=False."""
        with patch("birdbird.songs.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)

            extract_audio_segment(
                Path("input.avi"), Path("out.wav"),
                start_s=5.0, end_s=8.0, normalize=False,
            )

        cmd = mock_run.call_args[0][0]
        assert "-af" not in cmd


class TestExtractSpeciesClips:
    """Tests for extract_species_clips()."""

    def test_picks_highest_confidence_per_species(self, tmp_path):
        """Extracts clip for highest confidence detection per species."""
        detections = [
            SongDetection("clip1.avi", "2026-01-14T08:30:15", 0.0, 3.0, "Blue Tit", "Cyanistes caeruleus", 0.7),
            SongDetection("clip2.avi", "2026-01-14T08:31:00", 5.0, 8.0, "Blue Tit", "Cyanistes caeruleus", 0.95),
            SongDetection("clip1.avi", "2026-01-14T08:30:15", 2.0, 5.0, "Robin", "Erithacus rubecula", 0.8),
        ]

        input_dir = tmp_path / "input"
        input_dir.mkdir()
        (input_dir / "clip1.avi").touch()
        (input_dir / "clip2.avi").touch()
        output_dir = tmp_path / "output"

        with patch("birdbird.songs.extract_audio_segment", return_value=True):
            clips = extract_species_clips(detections, input_dir, output_dir)

        assert len(clips) == 2
        # Blue Tit should use clip2.avi (higher confidence)
        bt_clip = [c for c in clips if c["common_name"] == "Blue Tit"][0]
        assert bt_clip["source_file"] == "clip2.avi"
        assert bt_clip["confidence"] == 0.95

    def test_empty_detections(self, tmp_path):
        """Empty detections returns empty list."""
        clips = extract_species_clips([], tmp_path, tmp_path / "output")
        assert clips == []


class TestAnalyzeSongs:
    """Tests for analyze_songs()."""

    @patch("birdbird.songs.suppress_stdout")
    @patch("birdbird.songs.extract_audio")
    def test_full_pipeline(self, mock_extract, mock_suppress, tmp_path):
        """Full pipeline with mocked BirdNET returns correct structure."""
        # Create input dir with AVI files
        input_dir = tmp_path / "20260114"
        input_dir.mkdir()
        (input_dir / "1408301500.avi").touch()

        mock_extract.return_value = True
        mock_suppress.return_value.__enter__ = MagicMock()
        mock_suppress.return_value.__exit__ = MagicMock(return_value=False)

        # Mock the BirdNET analyze function and CSV output
        def fake_analyze(**kwargs):
            # Create a CSV result file
            audio_input = Path(kwargs["audio_input"])
            output_dir = Path(kwargs["output"])
            csv_path = output_dir / f"{audio_input.stem}.BirdNET.results.csv"
            csv_path.write_text(
                "Start (s),End (s),Scientific name,Common name,Confidence,File\n"
                "0.0,3.0,Cyanistes caeruleus,Eurasian Blue Tit,0.91,test.wav\n"
            )

        with patch("birdnet_analyzer.analyze", fake_analyze):
            with patch("birdbird.songs.extract_species_clips", return_value=[]):
                result = analyze_songs(input_dir, min_confidence=0.5, extract_clips=False)

        assert "detections" in result
        assert "summary" in result
        assert "config" in result
        assert result["summary"]["total_detections"] == 1
        assert result["summary"]["unique_species"] == 1

    @patch("birdbird.songs.extract_audio")
    def test_no_audio_extracted(self, mock_extract, tmp_path):
        """Raises ValueError when no audio can be extracted."""
        input_dir = tmp_path / "20260114"
        input_dir.mkdir()
        (input_dir / "1408301500.avi").touch()

        mock_extract.return_value = False

        with pytest.raises(ValueError, match="Failed to extract audio"):
            analyze_songs(input_dir)


class TestSaveSongDetections:
    """Tests for save_song_detections()."""

    def test_writes_valid_json(self, tmp_path):
        """File contents match the input dict."""
        results = {
            "config": {"min_confidence": 0.5},
            "detections": [{"common_name": "Blue Tit", "confidence": 0.9}],
            "summary": {"total_detections": 1},
        }
        output_path = tmp_path / "songs.json"

        save_song_detections(results, output_path)

        assert output_path.exists()
        with open(output_path) as f:
            loaded = json.load(f)
        assert loaded == results
