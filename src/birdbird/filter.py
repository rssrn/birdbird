"""Clip filtering logic.

@author Claude Opus 4.5 Anthropic
"""

import json
import os
import shutil
from pathlib import Path
from typing import Any

from tqdm import tqdm

from .detector import BirdDetector
from .paths import BirdbirdPaths


def create_symlink_or_copy(src: Path, dst: Path) -> None:
    """Create symlink to src at dst. Falls back to copy on Windows/errors.

    Args:
        src: Source file path
        dst: Destination path for symlink or copy
    """
    try:
        os.symlink(src, dst)
    except (OSError, NotImplementedError):
        # Windows or filesystem doesn't support symlinks
        shutil.copy2(src, dst)


def filter_clips(
    input_dir: Path,
    bird_confidence: float = 0.2,
    limit: int | None = None,
) -> dict:
    """Filter clips to keep only those containing birds.

    Saves detection metadata to detections.json in the working filter directory.
    Creates symlinks to filtered clips (falls back to copies on Windows).

    Args:
        input_dir: Directory containing .avi clips
        bird_confidence: Minimum confidence threshold for bird detection
        limit: Maximum number of clips to process (for testing)

    Returns:
        Dict with counts: total, with_birds, filtered_out, and paths object
    """
    input_dir = Path(input_dir)
    paths = BirdbirdPaths.from_input_dir(input_dir)
    paths.ensure_working_dirs()

    clips = sorted(input_dir.glob("*.avi"))
    if limit:
        clips = clips[:limit]

    detector = BirdDetector(
        bird_confidence=bird_confidence,
    )

    stats: dict[str, Any] = {"total": len(clips), "with_birds": 0, "filtered_out": 0}
    detections: dict[str, dict] = {}

    for clip_path in tqdm(clips, desc="Processing clips"):
        detection = detector.detect_in_video_detailed(clip_path)

        if detection:
            stats["with_birds"] += 1
            dest = paths.clips_dir / clip_path.name
            if not dest.exists():
                create_symlink_or_copy(clip_path, dest)
            # Save detection metadata
            detections[clip_path.name] = {
                "first_bird": detection.timestamp,
                "confidence": round(detection.confidence, 3),
            }
        else:
            stats["filtered_out"] += 1

    # Write detections metadata
    with open(paths.detections_json, "w") as f:
        json.dump(detections, f, indent=2)

    stats["paths"] = paths
    return stats
