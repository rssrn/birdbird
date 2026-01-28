"""Find best clips for each species using rolling window confidence scoring.

This module analyzes species.json timeline data to identify the highest-confidence
time windows for each detected species, supporting seek functionality in the viewer.

@author Claude Sonnet 4.5 Anthropic
"""

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass
class BestClip:
    """Best time window for a species.

    @author Claude Sonnet 4.5 Anthropic
    """
    species: str
    start_s: float
    end_s: float
    score: float  # Sum of confidence values in window
    detection_count: int  # Number of detections in window


def find_best_clip_for_species(
    detections: list[dict],
    species: str,
    window_duration_s: float = 14.0,
) -> BestClip | None:
    """Find best time window for a species using sliding window scoring.

    Uses a two-pointer sliding window approach for O(n) time complexity.

    Args:
        detections: List of detection dicts with timestamp_s, species, confidence
        species: Species name to find best clip for
        window_duration_s: Duration of window in seconds (default 14)

    Returns:
        BestClip with highest score, or None if no detections for this species

    @author Claude Sonnet 4.5 Anthropic
    """
    # Filter detections for this species
    species_detections = [
        d for d in detections
        if d["species"] == species
    ]

    if not species_detections:
        return None

    # Sort by timestamp
    species_detections.sort(key=lambda d: d["timestamp_s"])

    # Sliding window with two pointers - O(n) algorithm
    best_score = 0.0
    best_start_idx = 0
    best_count = 0

    current_score = 0.0
    window_start = 0

    # Expand window by moving end pointer
    for window_end in range(len(species_detections)):
        # Add current detection to window
        current_score += species_detections[window_end]["confidence"]

        # Shrink window from left while detections fall outside window duration
        window_start_time = species_detections[window_start]["timestamp_s"]
        window_end_time = species_detections[window_end]["timestamp_s"]

        while (window_end_time - window_start_time) > window_duration_s:
            current_score -= species_detections[window_start]["confidence"]
            window_start += 1
            window_start_time = species_detections[window_start]["timestamp_s"]

        # Check if this is the best window so far
        if current_score > best_score:
            best_score = current_score
            best_start_idx = window_start
            best_count = window_end - window_start + 1

    best_start = species_detections[best_start_idx]["timestamp_s"]
    best_end = best_start + window_duration_s

    return BestClip(
        species=species,
        start_s=best_start,
        end_s=best_end,
        score=round(best_score, 3),
        detection_count=best_count,
    )


def find_all_best_clips(
    species_json_path: Path,
    window_duration_s: float = 14.0,
) -> dict[str, BestClip]:
    """Find best clips for all species in species.json.

    Args:
        species_json_path: Path to species.json file
        window_duration_s: Duration of window in seconds (default 14)

    Returns:
        Dict mapping species name to BestClip

    @author Claude Sonnet 4.5 Anthropic
    """
    if not species_json_path.exists():
        raise FileNotFoundError(f"Species data not found: {species_json_path}")

    with open(species_json_path) as f:
        data = json.load(f)

    detections = data.get("detections", [])
    species_list = list(data.get("species_summary", {}).keys())

    best_clips = {}
    for species in species_list:
        clip = find_best_clip_for_species(detections, species, window_duration_s)
        if clip:
            best_clips[species] = clip

    return best_clips


def save_best_clips(
    best_clips: dict[str, BestClip],
    output_path: Path,
    window_duration_s: float = 14.0,
) -> None:
    """Save best clips data to JSON file.

    Args:
        best_clips: Dict mapping species to BestClip
        output_path: Path to output JSON file
        window_duration_s: Window duration used (for metadata)

    @author Claude Sonnet 4.5 Anthropic
    """
    data = {
        "window_duration_s": window_duration_s,
        "species_count": len(best_clips),
        "clips": {
            species: {
                "start_s": clip.start_s,
                "end_s": clip.end_s,
                "score": clip.score,
                "detection_count": clip.detection_count,
            }
            for species, clip in best_clips.items()
        }
    }

    with open(output_path, "w") as f:
        json.dump(data, f, indent=2)
