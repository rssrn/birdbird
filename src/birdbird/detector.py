"""YOLO-based bird detection.

@author Claude Opus 4.5 Anthropic
"""

from pathlib import Path

import cv2
import numpy as np
from ultralytics import YOLO


class BirdDetector:
    """Detects birds in images using YOLOv8-nano."""

    BIRD_CLASS_ID = 14  # COCO class ID for 'bird'
    PERSON_CLASS_ID = 0  # COCO class ID for 'person' (close-up birds often misclassified)

    def __init__(
        self,
        bird_confidence: float = 0.2,
        person_confidence: float = 0.3,
    ):
        self.bird_confidence = bird_confidence
        self.person_confidence = person_confidence
        self.model = YOLO("yolov8n.pt")

    def detect_in_frame(self, frame: np.ndarray) -> bool:
        """Check if a frame contains a bird (or person, which may be a close-up bird).

        Args:
            frame: BGR image as numpy array

        Returns:
            True if bird or person detected with sufficient confidence
        """
        results = self.model(frame, verbose=False)
        for result in results:
            boxes = result.boxes
            if boxes is None:
                continue
            for cls, conf in zip(boxes.cls, boxes.conf):
                cls_id = int(cls)
                if cls_id == self.BIRD_CLASS_ID and conf >= self.bird_confidence:
                    return True
                if cls_id == self.PERSON_CLASS_ID and conf >= self.person_confidence:
                    return True
        return False

    def detect_in_video(self, video_path: Path) -> bool:
        """Check if a video contains birds by sampling frames.

        Uses weighted sampling: ~4 samples in first second (where motion
        triggered), then 1fps for the remainder.

        Args:
            video_path: Path to video file

        Returns:
            True if any sampled frame contains a bird
        """
        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            return False

        video_fps = cap.get(cv2.CAP_PROP_FPS)
        first_second_frames = int(video_fps)  # frames in first second
        # Sample ~4 times in first second, then 1fps after
        early_interval = max(1, int(video_fps / 4))  # every 0.25s
        late_interval = max(1, int(video_fps))  # every 1s
        frame_count = 0

        try:
            while True:
                ret, frame = cap.read()
                if not ret:
                    break

                # Denser sampling in first second, 1fps after
                interval = early_interval if frame_count < first_second_frames else late_interval

                if frame_count % interval == 0:
                    if self.detect_in_frame(frame):
                        return True

                frame_count += 1
        finally:
            cap.release()

        return False
