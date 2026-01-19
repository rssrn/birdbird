"""Frame extraction and quality scoring.

@author Claude Sonnet 4.5 Anthropic
"""

import json
import time
from dataclasses import dataclass, asdict
from pathlib import Path

import cv2
import numpy as np
from tqdm import tqdm

from .detector import BirdDetector
from .filter import load_detections


@dataclass
class FrameScore:
    """Individual frame scoring details.

    @author Claude Sonnet 4.5 Anthropic
    """
    clip_name: str
    timestamp: float
    confidence: float      # From detection
    sharpness: float       # Variance of Laplacian
    bird_size: float       # Bbox area as % of frame
    position: float        # Center-weighted score
    combined: float        # Weighted sum


def calculate_sharpness(frame: np.ndarray) -> float:
    """Variance of Laplacian - measures blur/focus.

    Higher values indicate sharper images. Typical range: 0-5000+

    @author Claude Sonnet 4.5 Anthropic
    """
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    return cv2.Laplacian(gray, cv2.CV_64F).var()


def calculate_bird_size(detector: BirdDetector, frame: np.ndarray) -> float:
    """Get bounding box area as % of frame.

    Returns 0.0 if no detection, otherwise bbox_area / frame_area.
    Larger birds (filling more of the frame) score higher.

    @author Claude Sonnet 4.5 Anthropic
    """
    # Run YOLO to get bounding boxes
    results = detector.model(frame, verbose=False)

    if not results or len(results) == 0:
        return 0.0

    frame_height, frame_width = frame.shape[:2]
    frame_area = frame_width * frame_height

    max_bbox_ratio = 0.0

    for result in results:
        boxes = result.boxes
        if boxes is None or len(boxes) == 0:
            continue

        for box in boxes:
            class_id = int(box.cls[0])
            conf = float(box.conf[0])

            # Check if it's a bird detection above threshold
            is_bird = (class_id == detector.BIRD_CLASS_ID and conf >= detector.bird_confidence)

            if is_bird:
                # Get bbox coordinates (xyxy format)
                x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
                bbox_width = x2 - x1
                bbox_height = y2 - y1
                bbox_area = bbox_width * bbox_height
                bbox_ratio = bbox_area / frame_area
                max_bbox_ratio = max(max_bbox_ratio, bbox_ratio)

    return max_bbox_ratio


def calculate_position(detector: BirdDetector, frame: np.ndarray) -> float:
    """Binary edge-clipping check (0.3 or 1.0).

    Returns 1.0 if bird bbox doesn't touch left/right/top edges (within 10px).
    Returns 0.3 (penalty) if bbox touches those edges.
    Touching bottom edge is neutral (bird on perch).

    @author Claude Sonnet 4.5 Anthropic
    """
    # Run YOLO to get bounding boxes
    results = detector.model(frame, verbose=False)

    if not results or len(results) == 0:
        return 0.0

    frame_height, frame_width = frame.shape[:2]
    edge_threshold = 10  # pixels

    best_position_score = 0.0

    for result in results:
        boxes = result.boxes
        if boxes is None or len(boxes) == 0:
            continue

        for box in boxes:
            class_id = int(box.cls[0])
            conf = float(box.conf[0])

            # Check if it's a bird detection above threshold
            is_bird = (class_id == detector.BIRD_CLASS_ID and conf >= detector.bird_confidence)

            if is_bird:
                # Get bbox coordinates
                x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()

                # Check if bbox touches problematic edges
                touches_left = x1 <= edge_threshold
                touches_right = x2 >= (frame_width - edge_threshold)
                touches_top = y1 <= edge_threshold
                # Bottom is OK (perch location), don't check

                if touches_left or touches_right or touches_top:
                    position_score = 0.3  # Partial penalty
                else:
                    position_score = 1.0  # Clear of edges

                best_position_score = max(best_position_score, position_score)

    return best_position_score


def normalize_scores(scores: dict[str, list[float]]) -> dict[str, list[float]]:
    """Normalize scoring factors to 0-1 range using min-max normalization.

    @author Claude Sonnet 4.5 Anthropic
    """
    normalized = {}
    for key, values in scores.items():
        if not values or key == 'confidence':
            # Confidence is already 0-1, skip normalization
            normalized[key] = values
            continue

        min_val = min(values)
        max_val = max(values)

        if max_val - min_val < 1e-6:
            # All values the same, set to 0.5
            normalized[key] = [0.5] * len(values)
        else:
            normalized[key] = [(v - min_val) / (max_val - min_val) for v in values]

    return normalized


def extract_and_score_frames(
    input_dir: Path,
    detector: BirdDetector,
    weights: dict[str, float],
    limit: int | None = None,
) -> tuple[list[FrameScore], dict]:
    """Extract and score all detected frames.

    Returns:
        Tuple of (scored_frames, timing_stats)

    @author Claude Sonnet 4.5 Anthropic
    """
    # Load detections
    detections = load_detections(input_dir)
    if not detections:
        return [], {}

    # Apply limit
    clip_names = sorted(detections.keys())
    if limit:
        clip_names = clip_names[:limit]

    # Collect raw scores before normalization
    raw_scores = {
        'confidence': [],
        'sharpness': [],
        'bird_size': [],
        'position': [],
    }

    # Timing accumulators
    timing_totals = {
        'confidence': 0.0,
        'sharpness': 0.0,
        'bird_size': 0.0,
        'position': 0.0,
    }

    frame_data = []  # Store (clip_name, timestamp, raw_scores_dict)

    # Extract and score frames
    for clip_name in tqdm(clip_names, desc="Scoring frames"):
        detection_info = detections[clip_name]
        timestamp = detection_info['first_bird']
        confidence = detection_info['confidence']

        clip_path = input_dir / clip_name
        if not clip_path.exists():
            continue

        # Open video and seek to timestamp
        cap = cv2.VideoCapture(str(clip_path))
        if not cap.isOpened():
            continue

        fps = cap.get(cv2.CAP_PROP_FPS)
        frame_num = int(timestamp * fps)
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_num)

        ret, frame = cap.read()
        cap.release()

        if not ret or frame is None:
            continue

        # Calculate each scoring factor with timing
        t0 = time.perf_counter()
        conf_score = confidence
        t1 = time.perf_counter()

        sharpness = calculate_sharpness(frame)
        t2 = time.perf_counter()

        bird_size = calculate_bird_size(detector, frame)
        t3 = time.perf_counter()

        position = calculate_position(detector, frame)
        t4 = time.perf_counter()

        # Accumulate timing
        timing_totals['confidence'] += (t1 - t0)
        timing_totals['sharpness'] += (t2 - t1)
        timing_totals['bird_size'] += (t3 - t2)
        timing_totals['position'] += (t4 - t3)

        # Store raw scores
        raw_scores['confidence'].append(conf_score)
        raw_scores['sharpness'].append(sharpness)
        raw_scores['bird_size'].append(bird_size)
        raw_scores['position'].append(position)

        frame_data.append({
            'clip_name': clip_name,
            'timestamp': timestamp,
            'confidence': conf_score,
            'sharpness': sharpness,
            'bird_size': bird_size,
            'position': position,
        })

    if not frame_data:
        return [], {}

    # Normalize scores to 0-1 range
    normalized = normalize_scores(raw_scores)

    # Calculate combined scores
    scored_frames = []
    for i, data in enumerate(frame_data):
        combined = (
            weights['confidence'] * normalized['confidence'][i] +
            weights['sharpness'] * normalized['sharpness'][i] +
            weights['bird_size'] * normalized['bird_size'][i] +
            weights['position'] * normalized['position'][i]
        )

        scored_frames.append(FrameScore(
            clip_name=data['clip_name'],
            timestamp=data['timestamp'],
            confidence=data['confidence'],
            sharpness=data['sharpness'],
            bird_size=data['bird_size'],
            position=data['position'],
            combined=combined,
        ))

    # Sort by combined score (descending)
    scored_frames.sort(key=lambda x: x.combined, reverse=True)

    # Calculate timing stats
    num_frames = len(frame_data)
    timing_stats = {
        'total_frames_scored': num_frames,
        'confidence_ms_per_frame': (timing_totals['confidence'] / num_frames) * 1000,
        'sharpness_ms_per_frame': (timing_totals['sharpness'] / num_frames) * 1000,
        'bird_size_ms_per_frame': (timing_totals['bird_size'] / num_frames) * 1000,
        'position_ms_per_frame': (timing_totals['position'] / num_frames) * 1000,
        'total_ms_per_frame': (sum(timing_totals.values()) / num_frames) * 1000,
    }

    return scored_frames, timing_stats


def save_top_frames(
    frames: list[FrameScore],
    input_dir: Path,
    output_dir: Path,
    top_n: int,
) -> list[Path]:
    """Save top N frames as JPEGs with descriptive filenames.

    @author Claude Sonnet 4.5 Anthropic
    """
    saved_paths = []

    for rank, frame_score in enumerate(frames[:top_n], start=1):
        clip_path = input_dir / frame_score.clip_name
        if not clip_path.exists():
            continue

        # Extract frame from clip
        cap = cv2.VideoCapture(str(clip_path))
        if not cap.isOpened():
            continue

        fps = cap.get(cv2.CAP_PROP_FPS)
        frame_num = int(frame_score.timestamp * fps)
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_num)

        ret, frame = cap.read()
        cap.release()

        if not ret or frame is None:
            continue

        # Generate filename
        clip_base = frame_score.clip_name.replace('.avi', '')
        filename = f"frame_{rank:03d}_{clip_base}_{frame_score.timestamp:.1f}s_score_{frame_score.combined:.2f}.jpg"
        output_path = output_dir / filename

        # Save with high quality
        cv2.imwrite(str(output_path), frame, [cv2.IMWRITE_JPEG_QUALITY, 95])
        saved_paths.append(output_path)

    return saved_paths


def save_frame_metadata(
    frames: list[FrameScore],
    timing_stats: dict,
    output_path: Path,
    config: dict,
) -> None:
    """Save frame_scores.json with all metadata.

    @author Claude Sonnet 4.5 Anthropic
    """
    frames_data = []
    for rank, frame in enumerate(frames, start=1):
        frames_data.append({
            'rank': rank,
            'filename': f"frame_{rank:03d}_{frame.clip_name.replace('.avi', '')}_{frame.timestamp:.1f}s_score_{frame.combined:.2f}.jpg",
            'clip': frame.clip_name,
            'timestamp': float(frame.timestamp),
            'scores': {
                'confidence': round(float(frame.confidence), 3),
                'sharpness': round(float(frame.sharpness), 1),
                'bird_size': round(float(frame.bird_size), 3),
                'position': round(float(frame.position), 3),
                'combined': round(float(frame.combined), 3),
            }
        })

    metadata = {
        'frames': frames_data,
        'timing_stats': timing_stats,
        'config': config,
    }

    with open(output_path, 'w') as f:
        json.dump(metadata, f, indent=2)
