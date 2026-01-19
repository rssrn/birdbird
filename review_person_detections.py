#!/usr/bin/env python3
"""Extract frames from person-detected clips with both bird and person confidence.

Usage: python review_person_detections.py /path/to/batch/has_birds/
"""

import json
import sys
from pathlib import Path

import cv2
from tqdm import tqdm

# Import from birdbird package
from src.birdbird.detector import BirdDetector


def get_detection_confidences(detector: BirdDetector, frame):
    """Run YOLO and return both bird and person confidences (max of each class).

    Returns: (bird_conf, person_conf) tuple, where None means no detection
    """
    # Run with very low confidence threshold to capture ALL detections
    results = detector.model(frame, verbose=False, conf=0.01)

    bird_conf = None
    person_conf = None

    if results and len(results) > 0:
        for result in results:
            boxes = result.boxes
            if boxes is None or len(boxes) == 0:
                continue

            for box in boxes:
                class_id = int(box.cls[0])
                conf = float(box.conf[0])

                if class_id == detector.BIRD_CLASS_ID:
                    bird_conf = max(bird_conf or 0, conf)
                elif class_id == detector.PERSON_CLASS_ID:
                    person_conf = max(person_conf or 0, conf)

    return bird_conf, person_conf


def main():
    if len(sys.argv) != 2:
        print("Usage: python review_person_detections.py /path/to/batch/has_birds/")
        sys.exit(1)

    input_dir = Path(sys.argv[1])
    if not input_dir.is_dir():
        print(f"Error: {input_dir} is not a directory")
        sys.exit(1)

    # Load detections
    detections_file = input_dir / "detections.json"
    if not detections_file.exists():
        print(f"Error: {detections_file} not found")
        sys.exit(1)

    with open(detections_file) as f:
        detections = json.load(f)

    # Filter for person detections
    person_clips = {
        clip: info for clip, info in detections.items()
        if info.get('detection_type') == 'person'
    }

    print(f"Found {len(person_clips)} clips with person detection")

    if not person_clips:
        print("No person-detected clips to review")
        return

    # Create output directory
    output_dir = input_dir.parent / "person_detection_review"
    output_dir.mkdir(exist_ok=True)
    print(f"Saving frames to: {output_dir}")

    # Initialize detector with same thresholds used during filtering
    detector = BirdDetector(bird_confidence=0.2, person_confidence=0.3)

    # Process each clip
    print("\nExtracting frames and detecting confidences...")
    for clip_name, detection_info in tqdm(list(person_clips.items())):
        clip_path = input_dir / clip_name
        if not clip_path.exists():
            continue

        # Open video and read sequentially to detection frame (same as original detector)
        cap = cv2.VideoCapture(str(clip_path))
        if not cap.isOpened():
            continue

        fps = cap.get(cv2.CAP_PROP_FPS)
        timestamp = detection_info['first_bird']  # Actually first_detection
        target_frame_num = int(timestamp * fps)

        # Read sequentially to exact frame (same as detector does)
        frame = None
        frame_count = 0
        while True:
            ret, current_frame = cap.read()
            if not ret:
                break
            if frame_count == target_frame_num:
                frame = current_frame
                break
            frame_count += 1

        cap.release()

        if frame is None:
            continue

        # Get both bird and person confidences
        bird_conf, person_conf = get_detection_confidences(detector, frame)

        # Format confidences for filename (3 digits, or 'none')
        bird_str = f"{int(bird_conf * 1000):03d}" if bird_conf else "none"
        person_str = f"{int(person_conf * 1000):03d}" if person_conf else "none"

        # Generate filename: clipname_bird050_person367.jpg
        clip_base = clip_name.replace('.avi', '')
        filename = f"{clip_base}_bird{bird_str}_person{person_str}.jpg"
        output_path = output_dir / filename

        # Save frame with high quality
        cv2.imwrite(str(output_path), frame, [cv2.IMWRITE_JPEG_QUALITY, 95])

    print(f"\nComplete! Saved {len(person_clips)} frames to {output_dir}")
    print("\nFilename format: clipname_birdXXX_personYYY.jpg")
    print("  - XXX/YYY are confidence values (0-999, e.g., 367 = 0.367)")
    print("  - 'none' means no detection of that class")
    print("\nReview the images to count:")
    print("  - Actual birds (true positives)")
    print("  - False positives (decorations, etc.)")


if __name__ == "__main__":
    main()
