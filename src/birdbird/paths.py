"""Centralized path management for birdbird pipeline.

This module defines the folder structure for the birdbird pipeline,
organizing files into working directories (temporary/intermediate)
and assets directories (final outputs mirroring R2 structure).

@author Claude Sonnet 4.5 Anthropic
"""

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass
class BirdbirdPaths:
    """Centralized path structure for birdbird pipeline.

    Structure:
        /input_dir/
        ├── *.avi (originals - unchanged)
        └── birdbird/
            ├── working/
            │   ├── filter/
            │   │   ├── clips/           (symlinks to filtered .avi files)
            │   │   └── detections.json  (detection metadata)
            │   └── frames/
            │       ├── candidates/      (all scored frames with detailed filenames)
            │       └── frame_scores.json (scoring metadata)
            └── assets/                  (mirrors R2 structure)
                ├── highlights.mp4
                ├── frame_01.jpg         (top 3 frames, simple numbering)
                ├── frame_02.jpg
                ├── frame_03.jpg
                ├── metadata.json        (batch metadata)
                ├── songs.json
                ├── species.json         (future)
                └── song_clips/
                    └── *.wav
    """
    input_dir: Path

    # Root birdbird directory
    birdbird_dir: Path

    # Working directories
    working_dir: Path
    filter_dir: Path
    clips_dir: Path
    detections_json: Path
    frames_working_dir: Path
    frames_candidates_dir: Path
    frame_scores_json: Path

    # Assets directory (mirrors R2)
    assets_dir: Path
    highlights_mp4: Path
    metadata_json: Path
    songs_json: Path
    species_json: Path
    song_clips_dir: Path

    @classmethod
    def from_input_dir(cls, input_dir: Path) -> 'BirdbirdPaths':
        """Initialize all paths from input directory.

        Args:
            input_dir: Path to directory containing original .avi clips

        Returns:
            BirdbirdPaths instance with all paths initialized
        """
        input_dir = Path(input_dir)
        birdbird_dir = input_dir / "birdbird"

        # Working paths
        working_dir = birdbird_dir / "working"
        filter_dir = working_dir / "filter"
        clips_dir = filter_dir / "clips"
        detections_json = filter_dir / "detections.json"
        frames_working_dir = working_dir / "frames"
        frames_candidates_dir = frames_working_dir / "candidates"
        frame_scores_json = frames_working_dir / "frame_scores.json"

        # Assets paths
        assets_dir = birdbird_dir / "assets"
        highlights_mp4 = assets_dir / "highlights.mp4"
        metadata_json = assets_dir / "metadata.json"
        songs_json = assets_dir / "songs.json"
        species_json = assets_dir / "species.json"
        song_clips_dir = assets_dir / "song_clips"

        return cls(
            input_dir=input_dir,
            birdbird_dir=birdbird_dir,
            working_dir=working_dir,
            filter_dir=filter_dir,
            clips_dir=clips_dir,
            detections_json=detections_json,
            frames_working_dir=frames_working_dir,
            frames_candidates_dir=frames_candidates_dir,
            frame_scores_json=frame_scores_json,
            assets_dir=assets_dir,
            highlights_mp4=highlights_mp4,
            metadata_json=metadata_json,
            songs_json=songs_json,
            species_json=species_json,
            song_clips_dir=song_clips_dir,
        )

    def ensure_working_dirs(self) -> None:
        """Create all working directories."""
        self.clips_dir.mkdir(parents=True, exist_ok=True)
        self.frames_candidates_dir.mkdir(parents=True, exist_ok=True)

    def ensure_assets_dirs(self) -> None:
        """Create assets directory structure."""
        self.assets_dir.mkdir(parents=True, exist_ok=True)
        self.song_clips_dir.mkdir(parents=True, exist_ok=True)


def get_asset_frame_paths(assets_dir: Path, top_n: int = 3) -> list[Path]:
    """Get paths for top N asset frames (frame_01.jpg, frame_02.jpg, etc.).

    Args:
        assets_dir: Path to assets directory
        top_n: Number of frame paths to generate (default: 3)

    Returns:
        List of Path objects for asset frames
    """
    return [assets_dir / f"frame_{i:02d}.jpg" for i in range(1, top_n + 1)]


def load_detections(detections_path: Path) -> dict:
    """Load detections.json from path.

    Args:
        detections_path: Path to detections.json file

    Returns:
        Dict mapping clip filenames to detection metadata.
        Format: {clip_name: {"first_bird": float, "confidence": float}}

    Raises:
        FileNotFoundError: If detections file doesn't exist
    """
    if not detections_path.exists():
        raise FileNotFoundError(
            f"Detections file not found: {detections_path}\n"
            f"Run 'birdbird filter' first to generate detections."
        )

    with open(detections_path) as f:
        return json.load(f)
