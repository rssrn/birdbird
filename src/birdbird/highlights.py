"""Highlights reel generation.

@author Claude Opus 4.5 Anthropic
"""

import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

import cv2
from tqdm import tqdm

from .detector import BirdDetector
from .paths import BirdbirdPaths, load_detections


# Cache for hardware encoder availability
_hardware_encoder_cache = None


def detect_hardware_encoder() -> str | None:
    """Detect available hardware H.264 encoder by actually testing it.

    Returns encoder name (e.g., 'h264_qsv', 'h264_vaapi') or None.

    @author Claude Sonnet 4.5 Anthropic
    """
    global _hardware_encoder_cache

    if _hardware_encoder_cache is not None:
        return _hardware_encoder_cache

    # Priority order: Intel QSV > VAAPI > V4L2
    preferred_encoders = ['h264_qsv', 'h264_vaapi', 'h264_v4l2m2m']

    try:
        result = subprocess.run(
            ['ffmpeg', '-hide_banner', '-encoders'],
            capture_output=True,
            text=True,
            timeout=5
        )

        for encoder in preferred_encoders:
            if encoder in result.stdout:
                # Actually test if the encoder works
                test_cmd = [
                    'ffmpeg', '-hide_banner',
                    '-f', 'lavfi', '-i', 'testsrc=duration=0.1:size=640x480:rate=30',
                    '-c:v', encoder,
                    '-f', 'null', '-'
                ]
                test_result = subprocess.run(
                    test_cmd,
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                if test_result.returncode == 0:
                    _hardware_encoder_cache = encoder
                    return encoder

    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    _hardware_encoder_cache = None
    return None


@dataclass
class Segment:
    """A segment of video containing bird activity."""
    clip_path: Path
    start_time: float
    end_time: float

    @property
    def duration(self) -> float:
        return self.end_time - self.start_time


@dataclass
class HighlightsStats:
    """Statistics about the highlights reel generation."""
    original_duration: float  # Total duration of all input clips
    bird_clips_duration: float  # Duration of clips that had birds
    final_duration: float  # Duration of the highlights reel
    clip_count: int  # Number of input clips
    segment_count: int  # Number of segments extracted

    def summary(self) -> str:
        return (
            f"Original footage: {self.original_duration / 60:.1f} min ({self.clip_count} clips)\n"
            f"Clips with birds: {self.bird_clips_duration / 60:.1f} min\n"
            f"Final highlights: {self.final_duration / 60:.1f} min ({self.segment_count} segments)"
        )


def get_video_duration(video_path: Path) -> float:
    """Get duration of a video in seconds."""
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        return 0.0
    fps = cap.get(cv2.CAP_PROP_FPS)
    frame_count = cap.get(cv2.CAP_PROP_FRAME_COUNT)
    cap.release()
    return frame_count / fps if fps > 0 else 0.0


def _detect_at_time(cap: cv2.VideoCapture, detector: BirdDetector, time_sec: float, fps: float) -> bool:
    """Seek to a specific time and run detection on that frame."""
    frame_num = int(time_sec * fps)
    cap.set(cv2.CAP_PROP_POS_FRAMES, frame_num)
    ret, frame = cap.read()
    if not ret:
        return False
    return detector.detect_in_frame(frame)


def find_bird_segments(
    video_path: Path,
    detector: BirdDetector,
    buffer_before: float = 1.0,
    buffer_after: float = 1.0,
    known_first_bird: float | None = None,
) -> list[Segment]:
    """Find segments of video containing birds using binary search.

    If known_first_bird is provided (from cached filter results), skips
    searching for the start point and only finds the end point.

    Args:
        video_path: Path to video file
        detector: BirdDetector instance
        buffer_before: Seconds to include before first bird detection
        buffer_after: Seconds to include after last bird detection
        known_first_bird: Timestamp of first bird from filter (skips start search)

    Returns:
        List of Segments with bird activity (usually 0 or 1 segment)
    """
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        return []

    fps = cap.get(cv2.CAP_PROP_FPS)
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    duration = frame_count / fps if fps > 0 else 0

    if duration < 1:
        cap.release()
        return []

    try:
        end_time = max(duration - 1.0, 1.0)

        if known_first_bird is not None:
            # We know where the bird first appears - just find the end
            first_bird_time = known_first_bird
            # Check if bird is still there at end
            if _detect_at_time(cap, detector, end_time, fps):
                last_bird_time = end_time
            else:
                # Binary search from known start to end
                last_bird_time = _binary_search_exit(cap, detector, first_bird_time, end_time, fps)
        else:
            # No cached data - search for both start and end
            check_times = [0.0, 0.5, duration / 3, duration * 2 / 3, end_time]

            first_bird_time = None
            last_bird_time = None

            for t in check_times:
                if _detect_at_time(cap, detector, t, fps):
                    if first_bird_time is None:
                        first_bird_time = t
                    last_bird_time = t

            if first_bird_time is None or last_bird_time is None:
                cap.release()
                return []

            # Refine start if not at frame 0
            if first_bird_time > 0:
                first_bird_time = _binary_search_entry(cap, detector, 0, first_bird_time, fps)

            # Refine end if not at clip end
            if last_bird_time < end_time:
                last_bird_time = _binary_search_exit(cap, detector, last_bird_time, end_time, fps)

        # Apply buffers (both times guaranteed non-None by guard above)
        assert first_bird_time is not None and last_bird_time is not None  # nosec B101
        segment_start = max(0, first_bird_time - buffer_before)
        segment_end = min(duration, last_bird_time + buffer_after)

        cap.release()
        return [Segment(clip_path=video_path, start_time=segment_start, end_time=segment_end)]

    except Exception:
        cap.release()
        return []


def _binary_search_exit(cap: cv2.VideoCapture, detector: BirdDetector,
                        low: float, high: float, fps: float, precision: float = 1.0) -> float:
    """Binary search to find when bird exits (last time with bird)."""
    last_seen = low
    while high - low > precision:
        mid = (low + high) / 2
        if _detect_at_time(cap, detector, mid, fps):
            last_seen = mid
            low = mid
        else:
            high = mid
    return last_seen


def _binary_search_entry(cap: cv2.VideoCapture, detector: BirdDetector,
                         low: float, high: float, fps: float, precision: float = 1.0) -> float:
    """Binary search to find when bird enters (first time with bird)."""
    first_seen = high
    while high - low > precision:
        mid = (low + high) / 2
        if _detect_at_time(cap, detector, mid, fps):
            first_seen = mid
            high = mid
        else:
            low = mid
    return first_seen


def extract_segment(
    segment: Segment,
    output_path: Path,
    threads: int = 2,
    optimize_web: bool = False,
) -> bool:
    """Extract a segment from a video using ffmpeg.

    Args:
        segment: Segment to extract
        output_path: Where to save the extracted segment
        threads: Max ffmpeg threads to use
        optimize_web: If True, optimize for web (1080p @ 24fps, CRF 23)

    Returns:
        True if successful

    @author Claude Sonnet 4.5 Anthropic
    """
    hw_encoder = detect_hardware_encoder()

    # Choose encoder and quality settings
    if hw_encoder:
        encoder = hw_encoder
        # Hardware encoders use different quality scales
        if hw_encoder == 'h264_qsv':
            # QSV uses -global_quality 1-51 (lower is better)
            quality_opts = ["-global_quality", "23" if optimize_web else "18"]
        elif hw_encoder in ['h264_vaapi', 'h264_v4l2m2m']:
            # VAAPI/V4L2 use -qp scale
            quality_opts = ["-qp", "23" if optimize_web else "18"]
        else:
            quality_opts = []
    else:
        encoder = "libx264"
        quality_opts = [
            "-preset", "fast",
            "-crf", "23" if optimize_web else "18",
        ]

    # Build base command
    cmd = [
        "ffmpeg", "-y",
        "-threads", str(threads),
        "-ss", str(segment.start_time),
        "-i", str(segment.clip_path),
        "-t", str(segment.duration),
    ]

    # Add video filter for web optimization (preserve aspect ratio, just reduce framerate)
    if optimize_web:
        cmd.extend(["-vf", "fps=24"])

    # Add encoding options
    cmd.extend([
        "-c:v", encoder,
        *quality_opts,
        "-c:a", "aac",
        "-loglevel", "error",
        str(output_path),
    ])

    result = subprocess.run(cmd, capture_output=True, text=True)

    # If hardware encoding failed, log and try falling back to software
    if result.returncode != 0 and hw_encoder:
        if result.stderr:
            print(f"\nHardware encoding failed for {segment.clip_path.name}: {result.stderr[:200]}")
        # Try again with libx264
        cmd_fallback = [
            "ffmpeg", "-y",
            "-threads", str(threads),
            "-ss", str(segment.start_time),
            "-i", str(segment.clip_path),
            "-t", str(segment.duration),
        ]

        if optimize_web:
            cmd_fallback.extend(["-vf", "fps=24"])

        cmd_fallback.extend([
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", "23" if optimize_web else "18",
            "-c:a", "aac",
            "-loglevel", "error",
            str(output_path),
        ])

        result = subprocess.run(cmd_fallback, capture_output=True, text=True)

    if result.returncode != 0 and result.stderr:
        # Print first error for debugging
        print(f"\nWarning: ffmpeg error for {segment.clip_path.name}: {result.stderr[:200]}")

    return result.returncode == 0


def concatenate_segments(
    segment_files: list[Path],
    output_path: Path,
    threads: int = 2,
) -> bool:
    """Concatenate video segments using simple concat (no transitions).

    Args:
        segment_files: List of video files to concatenate
        output_path: Where to save the final video
        threads: Max ffmpeg threads to use (not used for copy mode)

    Returns:
        True if successful

    @author Claude Sonnet 4.5 Anthropic
    """
    if not segment_files:
        return False

    if len(segment_files) == 1:
        # Single segment - just copy
        cmd = [
            "ffmpeg", "-y",
            "-i", str(segment_files[0]),
            "-c", "copy",
            "-loglevel", "error",
            str(output_path),
        ]
        result = subprocess.run(cmd, capture_output=True)
        return result.returncode == 0

    # Multiple segments - concat using demuxer (very fast, no re-encoding)
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
        for seg_file in segment_files:
            f.write(f"file '{seg_file}'\n")
        concat_list = f.name

    cmd = [
        "ffmpeg", "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", concat_list,
        "-c", "copy",
        "-loglevel", "error",
        str(output_path),
    ]
    result = subprocess.run(cmd, capture_output=True)
    Path(concat_list).unlink()
    return result.returncode == 0


def generate_highlights(
    input_dir: Path,
    output_path: Path,
    bird_confidence: float = 0.2,
    buffer_before: float = 1.0,
    buffer_after: float = 1.0,
    threads: int = 2,
    optimize_web: bool = False,
    original_duration: float | None = None,
    paths: BirdbirdPaths | None = None,
) -> HighlightsStats:
    """Generate a highlights reel from bird clips.

    Args:
        input_dir: Directory containing .avi clips (already filtered for birds)
        output_path: Where to save the highlights MP4
        bird_confidence: Confidence threshold for bird detection
        buffer_before: Seconds to include before first bird detection
        buffer_after: Seconds to include after last bird detection (bird-free)
        threads: Max ffmpeg threads to use (default 2 for low-power systems)
        optimize_web: If True, optimize for web viewing (preserve aspect ratio @ 24fps, CRF 23)
        original_duration: Optional pre-calculated original duration (if None, calculates from input_dir)
        paths: Optional BirdbirdPaths object (constructed if not provided)

    Returns:
        HighlightsStats with duration information

    @author Claude Sonnet 4.5 Anthropic
    """
    clips = sorted(input_dir.glob("*.avi"))
    if not clips:
        raise ValueError(f"No .avi clips found in {input_dir}")

    # Get paths if not provided
    if paths is None:
        # Try to infer from input_dir (which should be clips_dir)
        # Go up 3 levels: clips -> filter -> working -> birdbird -> input_dir
        paths = BirdbirdPaths.from_input_dir(input_dir.parent.parent.parent.parent)

    # Detect hardware encoder once at start
    hw_encoder = detect_hardware_encoder()
    if hw_encoder:
        print(f"Using hardware encoder: {hw_encoder}")
    else:
        print(f"Using software encoder: libx264")

    print(f"FFmpeg thread limit: {threads}")

    # Try to load cached detection data from filter step
    try:
        cached_detections = load_detections(paths.detections_json)
        using_cache = True
        print(f"Using cached detections for {len(cached_detections)} clips")
    except FileNotFoundError:
        cached_detections = None
        using_cache = False

    detector = BirdDetector(
        bird_confidence=bird_confidence,
    )

    # Calculate original duration if not provided
    if original_duration is None:
        original_duration = sum(get_video_duration(c) for c in clips)

    # Find all segments
    all_segments: list[Segment] = []
    bird_clips_duration = 0.0

    for clip in tqdm(clips, desc="Finding bird segments"):
        # Use cached first_bird timestamp if available
        known_first_bird = None
        if cached_detections and clip.name in cached_detections:
            known_first_bird = cached_detections[clip.name].get("first_bird")

        segments = find_bird_segments(
            clip, detector, buffer_before, buffer_after, known_first_bird
        )
        if segments:
            bird_clips_duration += get_video_duration(clip)
            all_segments.extend(segments)

    if not all_segments:
        raise ValueError("No bird segments found in any clips")

    # Extract segments to temp files
    with tempfile.TemporaryDirectory() as tmpdir:
        segment_files: list[Path] = []

        for i, segment in enumerate(tqdm(all_segments, desc="Extracting segments")):
            seg_path = Path(tmpdir) / f"segment_{i:04d}.mp4"
            if extract_segment(segment, seg_path, threads, optimize_web):
                segment_files.append(seg_path)

        if not segment_files:
            raise ValueError("Failed to extract any segments")

        # Concatenate segments (simple concat, no transitions)
        print("Concatenating segments...")
        success = concatenate_segments(segment_files, output_path, threads)

        if not success:
            raise RuntimeError("Failed to concatenate segments")

    final_duration = get_video_duration(output_path)

    return HighlightsStats(
        original_duration=original_duration,
        bird_clips_duration=bird_clips_duration,
        final_duration=final_duration,
        clip_count=len(clips),
        segment_count=len(all_segments),
    )
