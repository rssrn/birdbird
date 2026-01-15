"""Clip filtering logic.

@author Claude Opus 4.5 Anthropic
"""

import shutil
from pathlib import Path

from tqdm import tqdm

from .detector import BirdDetector


def filter_clips(
    input_dir: Path,
    bird_confidence: float = 0.2,
    person_confidence: float = 0.3,
    limit: int | None = None,
) -> dict:
    """Filter clips to keep only those containing birds.

    Args:
        input_dir: Directory containing .avi clips
        bird_confidence: Minimum confidence threshold for bird detection
        person_confidence: Minimum confidence for person detection (close-up birds)
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
        person_confidence=person_confidence,
    )

    stats = {"total": len(clips), "with_birds": 0, "filtered_out": 0}

    for clip_path in tqdm(clips, desc="Processing clips"):
        has_bird = detector.detect_in_video(clip_path)

        if has_bird:
            stats["with_birds"] += 1
            dest = output_dir / clip_path.name
            if not dest.exists():
                shutil.copy2(clip_path, dest)
        else:
            stats["filtered_out"] += 1

    return stats
