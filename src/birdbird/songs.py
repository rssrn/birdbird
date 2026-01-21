"""Bird song detection using BirdNET.

Extracts audio from AVI files and analyzes for bird vocalizations.

@author Claude Opus 4.5 Anthropic
"""

import csv
import io
import json
import os
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from tqdm import tqdm


@contextmanager
def suppress_stdout():
    """Temporarily suppress stdout and stderr.

    @author Claude Opus 4.5 Anthropic
    """
    # Save original file descriptors
    stdout_fd = sys.stdout.fileno()
    stderr_fd = sys.stderr.fileno()
    saved_stdout_fd = os.dup(stdout_fd)
    saved_stderr_fd = os.dup(stderr_fd)

    # Redirect to devnull
    devnull = os.open(os.devnull, os.O_WRONLY)
    os.dup2(devnull, stdout_fd)
    os.dup2(devnull, stderr_fd)
    os.close(devnull)

    try:
        yield
    finally:
        # Restore original file descriptors
        os.dup2(saved_stdout_fd, stdout_fd)
        os.dup2(saved_stderr_fd, stderr_fd)
        os.close(saved_stdout_fd)
        os.close(saved_stderr_fd)


@dataclass
class SongDetection:
    """A single bird song detection."""

    filename: str  # Source AVI filename
    timestamp: str  # ISO format datetime when detection occurred
    start_s: float  # Start time within clip (seconds)
    end_s: float  # End time within clip (seconds)
    common_name: str  # e.g., "Eurasian Blue Tit"
    scientific_name: str  # e.g., "Cyanistes caeruleus"
    confidence: float  # 0.0 to 1.0

    def to_dict(self) -> dict:
        """Convert to JSON-serializable dict."""
        return {
            "filename": self.filename,
            "timestamp": self.timestamp,
            "start_s": self.start_s,
            "end_s": self.end_s,
            "common_name": self.common_name,
            "scientific_name": self.scientific_name,
            "confidence": round(self.confidence, 4),
        }


def extract_audio(
    avi_path: Path,
    output_path: Path,
    sample_rate: int = 48000,
) -> bool:
    """Extract audio from AVI file to WAV format.

    Args:
        avi_path: Path to source AVI file
        output_path: Path to output WAV file
        sample_rate: Sample rate for output (BirdNET default: 48000)

    Returns:
        True if extraction succeeded, False otherwise

    @author Claude Opus 4.5 Anthropic
    """
    cmd = [
        "ffmpeg",
        "-y",  # Overwrite output
        "-i",
        str(avi_path),
        "-vn",  # No video
        "-acodec",
        "pcm_s16le",  # 16-bit PCM
        "-ar",
        str(sample_rate),
        "-ac",
        "1",  # Mono
        str(output_path),
    ]

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
    )

    return result.returncode == 0


def parse_timestamp_from_filename(
    filename: str,
    dir_date: datetime | None,
) -> str | None:
    """Parse timestamp from AVI filename.

    Filename format: DDHHmmss00.avi
    - DD: day of month
    - HH: hour
    - mm: minute
    - ss: second
    - 00: padding

    Year and month come from dir_date.

    Args:
        filename: AVI filename (e.g., "1408301500.avi")
        dir_date: Date from parent directory (provides year/month)

    Returns:
        ISO format datetime string, or None if parsing fails

    @author Claude Opus 4.5 Anthropic
    """
    if not filename.endswith(".avi") or len(filename) < 10:
        return None

    try:
        day = int(filename[0:2])
        hour = int(filename[2:4])
        minute = int(filename[4:6])
        second = int(filename[6:8])

        if dir_date is None:
            return None

        # Construct datetime using year/month from directory
        dt = datetime(
            year=dir_date.year,
            month=dir_date.month,
            day=day,
            hour=hour,
            minute=minute,
            second=second,
        )

        return dt.isoformat()

    except (ValueError, IndexError):
        return None


def parse_dir_date(input_dir: Path) -> datetime | None:
    """Parse date from directory name (format: YYYYMMDD).

    @author Claude Opus 4.5 Anthropic
    """
    dir_name = input_dir.name

    if len(dir_name) == 8 and dir_name.isdigit():
        try:
            year = int(dir_name[0:4])
            month = int(dir_name[4:6])
            day = int(dir_name[6:8])
            return datetime(year, month, day)
        except ValueError:
            pass

    return None


def validate_timestamps(input_dir: Path, dir_date: datetime | None) -> bool:
    """Check if camera timestamps in filenames are reliable.

    Compares day values from filenames against the directory date.
    If the directory day doesn't fall within the range of filename days,
    the camera clock was likely incorrect (e.g., reset after power loss).

    Args:
        input_dir: Directory containing .avi clips
        dir_date: Date parsed from directory name

    Returns:
        True if timestamps appear reliable, False otherwise

    @author Claude Opus 4.5 Anthropic
    """
    if dir_date is None:
        return False

    dir_day = dir_date.day

    # Extract days from filenames (format: DDHHmmss00.avi)
    avi_files = list(input_dir.glob("*.avi"))
    if not avi_files:
        return False

    filename_days = []
    for avi_path in avi_files:
        filename = avi_path.name
        if len(filename) >= 10 and filename[0:2].isdigit():
            try:
                day = int(filename[0:2])
                if 1 <= day <= 31:
                    filename_days.append(day)
            except ValueError:
                continue

    if not filename_days:
        return False

    min_day = min(filename_days)
    max_day = max(filename_days)

    # Check if directory day falls within filename day range
    # Handle month boundaries: if min_day > max_day, clips span month boundary
    if min_day <= max_day:
        # Normal case: days within same month
        return min_day <= dir_day <= max_day
    else:
        # Month boundary case: check if dir_day is >= min_day (end of prev month)
        # or <= max_day (start of current month)
        return (dir_day >= min_day) or (dir_day <= max_day)


def parse_birdnet_csv(
    csv_path: Path,
    source_filename: str,
    dir_date: datetime | None,
    timestamps_reliable: bool = True,
) -> list[SongDetection]:
    """Parse BirdNET CSV output into SongDetection objects.

    BirdNET CSV format:
    Start (s),End (s),Scientific name,Common name,Confidence,File

    When timestamps_reliable is False (camera clock was wrong), only the date
    portion is used (YYYY-MM-DD format) rather than full ISO timestamp.

    @author Claude Opus 4.5 Anthropic
    """
    detections = []

    if not csv_path.exists():
        return detections

    with open(csv_path, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                start_s = float(row["Start (s)"])
                end_s = float(row["End (s)"])
                confidence = float(row["Confidence"])
                scientific_name = row["Scientific name"]
                common_name = row["Common name"]

                if timestamps_reliable:
                    # Calculate timestamp: file timestamp + detection start time
                    base_timestamp = parse_timestamp_from_filename(
                        source_filename, dir_date
                    )
                    if base_timestamp:
                        # Add detection start time to base timestamp
                        base_dt = datetime.fromisoformat(base_timestamp)
                        detection_dt = base_dt.replace(
                            second=base_dt.second + int(start_s)
                        )
                        timestamp = detection_dt.isoformat()
                    else:
                        timestamp = ""
                else:
                    # Timestamps unreliable - use only date from directory
                    if dir_date:
                        timestamp = dir_date.strftime("%Y-%m-%d")
                    else:
                        timestamp = ""

                detection = SongDetection(
                    filename=source_filename,
                    timestamp=timestamp,
                    start_s=start_s,
                    end_s=end_s,
                    common_name=common_name,
                    scientific_name=scientific_name,
                    confidence=confidence,
                )
                detections.append(detection)

            except (KeyError, ValueError):
                continue

    return detections


def analyze_songs(
    input_dir: Path,
    min_confidence: float = 0.5,
    lat: float | None = None,
    lon: float | None = None,
    threads: int = 2,
    limit: int | None = None,
) -> dict:
    """Analyze bird songs from AVI files using BirdNET.

    Args:
        input_dir: Directory containing .avi clips
        min_confidence: Minimum confidence threshold (0.0-1.0)
        lat: Latitude for species filtering (optional)
        lon: Longitude for species filtering (optional)
        threads: Number of CPU threads for BirdNET
        limit: Max clips to process (for testing)

    Returns:
        Dict with detections, config, and summary

    @author Claude Opus 4.5 Anthropic
    """
    from birdnet_analyzer import analyze

    # Find all AVI files
    avi_files = sorted(input_dir.glob("*.avi"))
    if limit:
        avi_files = avi_files[:limit]

    if not avi_files:
        raise ValueError(f"No .avi files found in {input_dir}")

    # Parse directory date for timestamp reconstruction
    dir_date = parse_dir_date(input_dir)

    # Validate timestamps (camera clock may be wrong)
    timestamps_reliable = validate_timestamps(input_dir, dir_date)
    if not timestamps_reliable:
        print("Note: Camera timestamps appear incorrect, using date only")

    # Create temp directory for audio extraction and results
    with tempfile.TemporaryDirectory(prefix="birdbird_songs_") as temp_dir:
        temp_path = Path(temp_dir)
        audio_dir = temp_path / "audio"
        results_dir = temp_path / "results"
        audio_dir.mkdir()
        results_dir.mkdir()

        # Extract audio from each AVI file
        print(f"Extracting audio from {len(avi_files)} clips...")
        extracted_files = []
        for avi_path in tqdm(avi_files, desc="Extracting audio"):
            wav_path = audio_dir / f"{avi_path.stem}.wav"
            if extract_audio(avi_path, wav_path):
                extracted_files.append((avi_path.name, wav_path))

        if not extracted_files:
            raise ValueError("Failed to extract audio from any clips")

        print(f"Extracted audio from {len(extracted_files)} clips")

        # Run BirdNET analysis on each file with progress bar
        print(f"Running BirdNET analysis (min_conf={min_confidence})...")

        all_detections: list[SongDetection] = []

        for avi_name, wav_path in tqdm(extracted_files, desc="Analyzing songs"):
            # Build analyze kwargs for single file
            analyze_kwargs = {
                "audio_input": str(wav_path),
                "output": str(results_dir),
                "min_conf": min_confidence,
                "threads": threads,
                "rtype": "csv",
                "sensitivity": 1.0,
                "overlap": 0.0,
            }

            # Add location filtering if provided
            if lat is not None and lon is not None:
                analyze_kwargs["lat"] = lat
                analyze_kwargs["lon"] = lon

            # Run analysis for this file (suppress verbose BirdNET output)
            with suppress_stdout():
                analyze(**analyze_kwargs)

            # Parse CSV result for this file
            # BirdNET creates CSV with pattern: {filename}.BirdNET.results.csv
            csv_filename = f"{wav_path.stem}.BirdNET.results.csv"
            csv_path = results_dir / csv_filename

            detections = parse_birdnet_csv(
                csv_path, avi_name, dir_date, timestamps_reliable
            )
            all_detections.extend(detections)

    # Sort by confidence (highest first)
    all_detections.sort(key=lambda d: d.confidence, reverse=True)

    # Build summary
    unique_species = set(d.scientific_name for d in all_detections)
    files_with_detections = set(d.filename for d in all_detections)

    # Build config record
    config = {
        "min_confidence": min_confidence,
        "threads": threads,
        "sensitivity": 1.0,
    }
    if lat is not None and lon is not None:
        config["location"] = {"lat": lat, "lon": lon}

    # Include date from directory when available
    date_from_dir = dir_date.strftime("%Y-%m-%d") if dir_date else None

    return {
        "config": config,
        "timestamps_reliable": timestamps_reliable,
        "date": date_from_dir,
        "detections": [d.to_dict() for d in all_detections],
        "summary": {
            "total_detections": len(all_detections),
            "unique_species": len(unique_species),
            "species_list": sorted(unique_species),
            "files_processed": len(avi_files),
            "files_with_detections": len(files_with_detections),
        },
    }


def save_song_detections(
    results: dict,
    output_path: Path,
) -> None:
    """Save song detection results to JSON file.

    @author Claude Opus 4.5 Anthropic
    """
    with open(output_path, "w") as f:
        json.dump(results, f, indent=2)
