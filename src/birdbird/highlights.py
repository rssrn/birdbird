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
from .filter import load_detections


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

            if first_bird_time is None:
                cap.release()
                return []

            # Refine start if not at frame 0
            if first_bird_time > 0:
                first_bird_time = _binary_search_entry(cap, detector, 0, first_bird_time, fps)

            # Refine end if not at clip end
            if last_bird_time < end_time:
                last_bird_time = _binary_search_exit(cap, detector, last_bird_time, end_time, fps)

        # Apply buffers
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


def extract_segment(segment: Segment, output_path: Path) -> bool:
    """Extract a segment from a video using ffmpeg.

    Args:
        segment: Segment to extract
        output_path: Where to save the extracted segment

    Returns:
        True if successful
    """
    cmd = [
        "ffmpeg", "-y",
        "-ss", str(segment.start_time),
        "-i", str(segment.clip_path),
        "-t", str(segment.duration),
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "18",
        "-c:a", "aac",
        "-loglevel", "error",
        str(output_path),
    ]
    result = subprocess.run(cmd, capture_output=True)
    return result.returncode == 0


def concatenate_with_crossfade(
    segment_files: list[Path],
    output_path: Path,
    crossfade_duration: float = 0.5,
) -> bool:
    """Concatenate video segments with crossfade transitions.

    Args:
        segment_files: List of video files to concatenate
        output_path: Where to save the final video
        crossfade_duration: Duration of crossfade in seconds

    Returns:
        True if successful
    """
    if not segment_files:
        return False

    if len(segment_files) == 1:
        # Just copy the single segment
        cmd = [
            "ffmpeg", "-y",
            "-i", str(segment_files[0]),
            "-c", "copy",
            "-loglevel", "error",
            str(output_path),
        ]
        result = subprocess.run(cmd, capture_output=True)
        return result.returncode == 0

    # Build complex filter for crossfade
    # This uses the xfade filter between consecutive clips
    inputs = []
    for f in segment_files:
        inputs.extend(["-i", str(f)])

    # Build filter chain for crossfades
    # For n clips, we need n-1 xfade and acrossfade operations
    video_filters = []
    audio_filters = []
    n = len(segment_files)

    # Get durations of each segment for offset calculation
    durations = [get_video_duration(f) for f in segment_files]

    # Build video crossfades: [0:v][1:v]xfade -> v0, [v0][2:v]xfade -> v1, etc.
    # Build audio crossfades: [0:a][1:a]acrossfade -> a0, [a0][2:a]acrossfade -> a1, etc.

    cumulative_duration = durations[0]
    for i in range(1, n):
        offset = cumulative_duration - crossfade_duration
        if offset < 0:
            offset = 0

        if i == 1:
            prev_v_label = "0:v"
            prev_a_label = "0:a"
        else:
            prev_v_label = f"v{i-2}"
            prev_a_label = f"a{i-2}"

        curr_v_label = f"{i}:v"
        curr_a_label = f"{i}:a"
        out_v_label = f"v{i-1}" if i < n - 1 else "vout"
        out_a_label = f"a{i-1}" if i < n - 1 else "aout"

        # Video xfade with offset
        video_filters.append(
            f"[{prev_v_label}][{curr_v_label}]xfade=transition=fade:duration={crossfade_duration}:offset={offset}[{out_v_label}]"
        )

        # Audio acrossfade (duration only, no offset needed)
        audio_filters.append(
            f"[{prev_a_label}][{curr_a_label}]acrossfade=d={crossfade_duration}:c1=tri:c2=tri[{out_a_label}]"
        )

        # Update cumulative duration (subtract crossfade overlap)
        cumulative_duration += durations[i] - crossfade_duration

    filter_complex = ";".join(video_filters + audio_filters)

    cmd = [
        "ffmpeg", "-y",
        *inputs,
        "-filter_complex", filter_complex,
        "-map", "[vout]",
        "-map", "[aout]",
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "18",
        "-c:a", "aac",
        "-loglevel", "error",
        str(output_path),
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        # Print error and fall back to simple concat without crossfade
        print(f"Warning: Crossfade failed, falling back to simple concatenation")
        print(f"FFmpeg error: {result.stderr}")
        return concatenate_simple(segment_files, output_path)
    return True


def concatenate_simple(segment_files: list[Path], output_path: Path) -> bool:
    """Simple concatenation without transitions (fallback)."""
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
    person_confidence: float = 0.3,
    buffer_before: float = 1.0,
    buffer_after: float = 1.0,
    crossfade_duration: float = 0.5,
) -> HighlightsStats:
    """Generate a highlights reel from bird clips.

    Args:
        input_dir: Directory containing .avi clips (already filtered for birds)
        output_path: Where to save the highlights MP4
        bird_confidence: Confidence threshold for bird detection
        person_confidence: Confidence threshold for person detection
        buffer_before: Seconds to include before first bird detection
        buffer_after: Seconds to include after last bird detection (bird-free)
        crossfade_duration: Duration of crossfade transitions

    Returns:
        HighlightsStats with duration information
    """
    clips = sorted(input_dir.glob("*.avi"))
    if not clips:
        raise ValueError(f"No .avi clips found in {input_dir}")

    # Try to load cached detection data from filter step
    cached_detections = load_detections(input_dir)
    using_cache = cached_detections is not None
    if using_cache:
        print(f"Using cached detections for {len(cached_detections)} clips")

    detector = BirdDetector(
        bird_confidence=bird_confidence,
        person_confidence=person_confidence,
    )

    # Calculate original duration
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
            if extract_segment(segment, seg_path):
                segment_files.append(seg_path)

        if not segment_files:
            raise ValueError("Failed to extract any segments")

        # Concatenate with crossfade
        print("Concatenating segments with crossfade...")
        success = concatenate_with_crossfade(
            segment_files, output_path, crossfade_duration
        )

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
