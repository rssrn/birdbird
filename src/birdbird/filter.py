"""Clip filtering logic.

@author Claude Opus 4.5 Anthropic
"""

import json
import shutil
from pathlib import Path

from tqdm import tqdm

from .detector import BirdDetector


DETECTIONS_FILE = "detections.json"


def filter_clips(
    input_dir: Path,
    bird_confidence: float = 0.2,
    limit: int | None = None,
) -> dict:
    """Filter clips to keep only those containing birds.

    Saves detection metadata to detections.json in the output directory
    for use by the highlights command.

    Args:
        input_dir: Directory containing .avi clips
        bird_confidence: Minimum confidence threshold for bird detection
        limit: Maximum number of clips to process (for testing)

    Returns:
        Dict with counts: total, with_birds, filtered_out
    """
    input_dir = Path(input_dir)
    output_dir = input_dir / "has_birds"
    output_dir.mkdir(exist_ok=True)

    clips = sorted(input_dir.glob("*.avi"))
    if limit:
        clips = clips[:limit]

    detector = BirdDetector(
        bird_confidence=bird_confidence,
    )

    stats = {"total": len(clips), "with_birds": 0, "filtered_out": 0}
    detections: dict[str, dict] = {}

    for clip_path in tqdm(clips, desc="Processing clips"):
        detection = detector.detect_in_video_detailed(clip_path)

        if detection:
            stats["with_birds"] += 1
            dest = output_dir / clip_path.name
            if not dest.exists():
                shutil.copy2(clip_path, dest)
            # Save detection metadata
            detections[clip_path.name] = {
                "first_bird": detection.timestamp,
                "confidence": round(detection.confidence, 3),
            }
        else:
            stats["filtered_out"] += 1

    # Write detections metadata
    detections_path = output_dir / DETECTIONS_FILE
    with open(detections_path, "w") as f:
        json.dump(detections, f, indent=2)

    return stats


def load_detections(input_dir: Path) -> dict[str, dict] | None:
    """Load detection metadata from a directory.

    Args:
        input_dir: Directory containing detections.json

    Returns:
        Dict mapping clip names to detection info, or None if not found
    """
    detections_path = Path(input_dir) / DETECTIONS_FILE
    if not detections_path.exists():
        return None
    with open(detections_path) as f:
        return json.load(f)
