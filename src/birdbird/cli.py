"""Command-line interface.

@author Claude Opus 4.5 Anthropic
"""

import shutil
from pathlib import Path

import typer

from .config import get_location
from .filter import filter_clips, load_detections
from .highlights import generate_highlights, get_video_duration
from .frames import extract_and_score_frames, save_top_frames, save_frame_metadata
from .publish import publish_to_r2
from .songs import analyze_songs, save_song_detections

app = typer.Typer(help="Bird feeder video analysis pipeline")


def format_duration(seconds: float) -> str:
    """Format duration as MMm:SSs (e.g., '5m:23s' or '0m:45s').

    @author Claude Sonnet 4.5 Anthropic
    """
    minutes = int(seconds // 60)
    secs = int(seconds % 60)
    return f"{minutes}m:{secs:02d}s"


@app.command()
def filter(
    input_dir: Path = typer.Argument(..., help="Directory containing .avi clips"),
    bird_confidence: float = typer.Option(0.2, "--bird-conf", "-b", help="Min confidence for bird detection"),
    limit: int | None = typer.Option(None, "--limit", "-l", help="Max clips to process (for testing)"),
) -> None:
    """Filter clips to keep only those containing birds."""
    if not input_dir.is_dir():
        typer.echo(f"Error: {input_dir} is not a directory", err=True)
        raise typer.Exit(1)

    # Count clips and estimate duration (~2.3s per clip based on benchmarks)
    clips = sorted(input_dir.glob("*.avi"))
    clip_count = min(len(clips), limit) if limit else len(clips)
    est_seconds = clip_count * 2.3
    est_minutes = est_seconds / 60

    typer.echo(f"Processing {clip_count} clips in {input_dir} (estimated {est_minutes:.1f} minutes)")
    typer.echo(f"Settings: bird_conf={bird_confidence}")

    stats = filter_clips(
        input_dir,
        bird_confidence=bird_confidence,
        limit=limit,
    )

    typer.echo("")
    typer.echo("Results:")
    typer.echo(f"  Total clips:    {stats['total']}")
    typer.echo(f"  With birds:     {stats['with_birds']}")
    typer.echo(f"  Filtered out:   {stats['filtered_out']}")
    pct = 100 * stats['with_birds'] / stats['total'] if stats['total'] > 0 else 0
    typer.echo(f"  Detection rate: {pct:.1f}%")
    typer.echo(f"  Bird clips in:  {input_dir}/has_birds/")


@app.command()
def highlights(
    input_dir: Path = typer.Argument(..., help="Directory containing .avi clips (pre-filtered for birds)"),
    output: Path = typer.Option(None, "--output", "-o", help="Output MP4 path (default: input_dir/highlights.mp4)"),
    bird_confidence: float = typer.Option(0.2, "--bird-conf", "-b", help="Min confidence for bird detection"),
    buffer_before: float = typer.Option(1.0, "--buffer-before", help="Seconds before first bird detection"),
    buffer_after: float = typer.Option(1.0, "--buffer-after", help="Seconds after last bird detection (bird-free time)"),
    threads: int = typer.Option(2, "--threads", "-t", help="Max ffmpeg threads (default 2 for low-power systems)"),
    highest_quality: bool = typer.Option(False, "--highest-quality", help="Use highest quality (1440x1080 @ 30fps, larger file)"),
) -> None:
    """Generate a highlights reel from bird clips.

    By default, optimizes for web viewing (1440x1080 @ 24fps, smaller files).
    Use --highest-quality for maximum quality (30fps, larger files).
    """
    if not input_dir.is_dir():
        typer.echo(f"Error: {input_dir} is not a directory", err=True)
        raise typer.Exit(1)

    if output is None:
        output = input_dir / "highlights.mp4"

    # Count clips and estimate duration (~7s per clip with binary search + extraction)
    clips = list(input_dir.glob("*.avi"))
    clip_count = len(clips)
    est_seconds = clip_count * 7
    est_minutes = est_seconds / 60

    quality_mode = "highest quality" if highest_quality else "web optimized"
    typer.echo(f"Generating highlights from {clip_count} clips (estimated {est_minutes:.1f} minutes)")
    typer.echo(f"Settings: bird_conf={bird_confidence}, buffer_before={buffer_before}s, buffer_after={buffer_after}s, threads={threads}, quality={quality_mode}")

    try:
        stats = generate_highlights(
            input_dir=input_dir,
            output_path=output,
            bird_confidence=bird_confidence,
            buffer_before=buffer_before,
            buffer_after=buffer_after,
            threads=threads,
            optimize_web=not highest_quality,
        )

        typer.echo("")
        typer.echo("Results:")
        typer.echo(stats.summary())
        typer.echo(f"Output: {output}")

    except ValueError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)
    except RuntimeError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)


@app.command()
def process(
    input_dir: Path = typer.Argument(..., help="Directory containing .avi clips"),
    output: Path = typer.Option(None, "--output", "-o", help="Output MP4 path (default: input_dir/has_birds/highlights.mp4)"),
    bird_confidence: float = typer.Option(0.2, "--bird-conf", "-b", help="Min confidence for bird detection"),
    song_confidence: float = typer.Option(0.5, "--song-conf", "-s", help="Min confidence for song detection (0.0-1.0)"),
    buffer_before: float = typer.Option(1.0, "--buffer-before", help="Seconds before first bird detection"),
    buffer_after: float = typer.Option(1.0, "--buffer-after", help="Seconds after last bird detection"),
    threads: int = typer.Option(2, "--threads", "-t", help="Max ffmpeg threads (default 2 for low-power systems)"),
    song_threads: int = typer.Option(2, "--song-threads", help="CPU threads for BirdNET"),
    top_n: int = typer.Option(20, "--top-n", "-n", help="Number of top frames to extract"),
    lat: float = typer.Option(None, "--lat", help="Latitude for species filtering (default: from config)"),
    lon: float = typer.Option(None, "--lon", help="Longitude for species filtering (default: from config)"),
    limit: int | None = typer.Option(None, "--limit", "-l", help="Max clips to process (for testing)"),
    force: bool = typer.Option(False, "--force", "-f", help="Clear existing has_birds directory without prompting"),
    highest_quality: bool = typer.Option(False, "--highest-quality", help="Use highest quality (1440x1080 @ 30fps, larger file)"),
) -> None:
    """Filter clips, generate highlights reel, extract top frames, and analyze songs.

    By default, optimizes for web viewing (1440x1080 @ 24fps, smaller files).
    Use --highest-quality for maximum quality (30fps, larger files).
    """
    if not input_dir.is_dir():
        typer.echo(f"Error: {input_dir} is not a directory", err=True)
        raise typer.Exit(1)

    # Estimate total time: ~2.3s filter + ~5s highlights + ~0.5s frames per clip with birds (~30% detection rate)
    clips = sorted(input_dir.glob("*.avi"))
    clip_count = min(len(clips), limit) if limit else len(clips)
    est_bird_clips = int(clip_count * 0.3)  # Assume ~30% have birds
    est_seconds = clip_count * 2.3 + est_bird_clips * (5 + 0.5)
    est_minutes = est_seconds / 60

    typer.echo(f"Processing {clip_count} clips (estimated {est_minutes:.1f} minutes total)")
    typer.echo(f"Settings: bird_conf={bird_confidence}, top_n={top_n}")
    typer.echo("")

    # Check if has_birds directory already exists with content
    has_birds_dir = input_dir / "has_birds"
    if has_birds_dir.exists():
        existing_clips = list(has_birds_dir.glob("*.avi"))
        if existing_clips:
            if force:
                typer.echo(f"Clearing existing {has_birds_dir} ({len(existing_clips)} clips)...")
                shutil.rmtree(has_birds_dir)
                typer.echo("")
            else:
                typer.echo(f"Warning: {has_birds_dir} already exists with {len(existing_clips)} clips")
                typer.echo("This will mix old and new results, which may cause cache mismatches.")
                typer.echo("")
                typer.echo("Options:")
                typer.echo("  1. Clear and start fresh (recommended)")
                typer.echo("  2. Continue anyway (may have issues)")
                typer.echo("  3. Cancel")
                typer.echo("")

                choice = typer.prompt("Choose option", type=int, default=1)

                if choice == 1:
                    typer.echo(f"Removing {has_birds_dir}...")
                    shutil.rmtree(has_birds_dir)
                elif choice == 2:
                    typer.echo("Continuing with existing directory (results may be unpredictable)")
                else:
                    typer.echo("Cancelled")
                    raise typer.Exit(0)
                typer.echo("")

    # Calculate original duration before filtering
    typer.echo("Calculating original duration...")
    clips_to_process = clips[:clip_count]
    original_duration = sum(get_video_duration(c) for c in clips_to_process)
    typer.echo("")

    # Step 1: Filter
    typer.echo("Step 1/4: Filtering clips...")
    filter_stats = filter_clips(
        input_dir,
        bird_confidence=bird_confidence,
        limit=limit,
    )

    pct = 100 * filter_stats['with_birds'] / filter_stats['total'] if filter_stats['total'] > 0 else 0
    typer.echo(f"  Found {filter_stats['with_birds']}/{filter_stats['total']} clips with birds ({pct:.1f}%)")
    typer.echo("")

    if filter_stats['with_birds'] == 0:
        typer.echo("No birds detected - skipping highlights and frames generation")
        raise typer.Exit(0)

    # Step 2: Highlights
    typer.echo("Step 2/4: Generating highlights...")
    has_birds_dir = input_dir / "has_birds"

    if output is None:
        output = has_birds_dir / "highlights.mp4"

    try:
        highlights_stats = generate_highlights(
            input_dir=has_birds_dir,
            output_path=output,
            bird_confidence=bird_confidence,
            buffer_before=buffer_before,
            buffer_after=buffer_after,
            threads=threads,
            optimize_web=not highest_quality,
            original_duration=original_duration,
        )

        typer.echo("")
        typer.echo(f"  Duration:   {format_duration(highlights_stats.final_duration)} highlights from {format_duration(highlights_stats.bird_clips_duration)} filtered from {format_duration(original_duration)} original")
        typer.echo("")

    except (ValueError, RuntimeError) as e:
        typer.echo(f"Error generating highlights: {e}", err=True)
        raise typer.Exit(1)

    # Step 3: Extract frames
    typer.echo("Step 3/4: Extracting top frames...")

    frames_dir = has_birds_dir / "frames"
    frames_dir.mkdir(exist_ok=True)

    # Track total wall clock time for frames
    import time
    start_time = time.perf_counter()

    # Scoring weights (tunable parameters)
    weights = {
        "bird_size": 0.25,    # Large birds are more visually impressive
        "sharpness": 0.30,    # Sharp focus important for quality
        "confidence": 0.25,   # Detection confidence
        "position": 0.20,     # Binary penalty for edge-clipped birds
    }

    # Extract and score
    from .detector import BirdDetector
    from .frames import extract_and_score_frames, save_top_frames, save_frame_metadata

    detector = BirdDetector(
        bird_confidence=bird_confidence,
    )

    try:
        scored_frames, timing_stats = extract_and_score_frames(
            input_dir=has_birds_dir,
            detector=detector,
            weights=weights,
            limit=None,  # Process all clips from filter step
        )

        if not scored_frames:
            typer.echo("  No frames found to score")
        else:
            # Save top N frames
            saved_paths = save_top_frames(
                frames=scored_frames,
                input_dir=has_birds_dir,
                output_dir=frames_dir,
                top_n=top_n,
            )

            # Save metadata
            metadata_path = frames_dir / "frame_scores.json"
            save_frame_metadata(
                frames=scored_frames[:top_n],
                timing_stats=timing_stats,
                output_path=metadata_path,
                config={"weights": weights, "top_n": top_n},
            )

            elapsed_seconds = time.perf_counter() - start_time
            typer.echo(f"  Extracted {len(saved_paths)} frames in {format_duration(elapsed_seconds)}")

        typer.echo("")

    except ValueError as e:
        typer.echo(f"Error extracting frames: {e}", err=True)
        raise typer.Exit(1)

    # Step 4: Analyze songs
    typer.echo("Step 4/4: Analyzing bird songs...")

    # Apply config defaults for location if not provided on CLI
    if lat is None and lon is None:
        config_lat, config_lon = get_location()
        if config_lat is not None and config_lon is not None:
            lat, lon = config_lat, config_lon

    # Validate location args (both or neither after config applied)
    if (lat is None) != (lon is None):
        typer.echo("  Error: --lat and --lon must both be provided for location filtering", err=True)
        typer.echo("  Skipping songs analysis")
        typer.echo("")
    else:
        songs_output = input_dir / "songs.json"

        # Remove existing songs.json if present
        if songs_output.exists():
            songs_output.unlink()

        try:
            songs_start = time.perf_counter()
            songs_results = analyze_songs(
                input_dir=input_dir,
                min_confidence=song_confidence,
                lat=lat,
                lon=lon,
                threads=song_threads,
                limit=limit,
            )

            # Save results
            save_song_detections(songs_results, songs_output)

            songs_elapsed = time.perf_counter() - songs_start
            typer.echo(f"  Detected {songs_results['summary']['total_detections']} songs ({songs_results['summary']['unique_species']} species) in {format_duration(songs_elapsed)}")
            typer.echo("")

        except Exception as e:
            typer.echo(f"  Error analyzing songs: {e}", err=True)
            typer.echo("  Continuing without songs data")
            typer.echo("")

    typer.echo("Complete!")
    typer.echo(f"  Bird clips: {has_birds_dir}/")
    typer.echo(f"  Highlights: {output}")
    typer.echo(f"  Frames:     {frames_dir}/")
    if (input_dir / "songs.json").exists():
        typer.echo(f"  Songs:      {input_dir}/songs.json")


@app.command()
def frames(
    input_dir: Path = typer.Argument(..., help="Directory containing filtered clips (has_birds/)"),
    output_dir: Path = typer.Option(None, "--output", "-o", help="Output directory (default: input_dir/frames/)"),
    top_n: int = typer.Option(20, "--top-n", "-n", help="Number of top frames to extract"),
    bird_confidence: float = typer.Option(0.2, "--bird-conf", "-b", help="Min confidence for bird detection"),
    limit: int | None = typer.Option(None, "--limit", "-l", help="Max clips to process (for testing)"),
    force: bool = typer.Option(False, "--force", "-f", help="Clear existing frames without prompting"),
) -> None:
    """Extract and rank best bird frames from filtered clips.

    @author Claude Sonnet 4.5 Anthropic
    """
    if not input_dir.is_dir():
        typer.echo(f"Error: {input_dir} is not a directory", err=True)
        raise typer.Exit(1)

    if output_dir is None:
        output_dir = input_dir / "frames"

    # Check if frames directory already exists with content
    if output_dir.exists():
        existing_frames = list(output_dir.glob("frame_*.jpg"))
        if existing_frames:
            if force:
                typer.echo(f"Clearing existing frames from {output_dir} ({len(existing_frames)} frames)...")
                for frame_file in existing_frames:
                    frame_file.unlink()
                # Also remove metadata if it exists
                metadata_file = output_dir / "frame_scores.json"
                if metadata_file.exists():
                    metadata_file.unlink()
                typer.echo("")
            else:
                typer.echo(f"Warning: {output_dir} already exists with {len(existing_frames)} frames")
                typer.echo("")
                typer.echo("Options:")
                typer.echo("  1. Clear and re-extract (recommended)")
                typer.echo("  2. Continue anyway (may mix old and new frames)")
                typer.echo("  3. Cancel")
                typer.echo("")

                choice = typer.prompt("Choose option", type=int, default=1)

                if choice == 1:
                    typer.echo(f"Removing existing frames from {output_dir}...")
                    for frame_file in existing_frames:
                        frame_file.unlink()
                    # Also remove metadata if it exists
                    metadata_file = output_dir / "frame_scores.json"
                    if metadata_file.exists():
                        metadata_file.unlink()
                    typer.echo("")
                elif choice == 2:
                    typer.echo("Continuing with existing directory (results may be unpredictable)")
                    typer.echo("")
                else:
                    typer.echo("Cancelled")
                    raise typer.Exit(0)

    output_dir.mkdir(exist_ok=True)

    # Check for detections.json
    detections_file = input_dir / "detections.json"
    if not detections_file.exists():
        typer.echo(f"Error: No detections.json found in {input_dir}", err=True)
        typer.echo("Run 'birdbird filter' first to generate detection metadata.", err=True)
        raise typer.Exit(1)

    # Load and count detections
    detections = load_detections(input_dir)
    clip_count = len(detections) if limit is None else min(len(detections), limit)

    # Estimate duration (~0.5s per frame for scoring)
    est_seconds = clip_count * 0.5
    est_minutes = est_seconds / 60

    typer.echo(f"Extracting frames from {clip_count} clips (estimated {est_minutes:.1f} minutes)")
    typer.echo(f"Settings: bird_conf={bird_confidence}, top_n={top_n}")
    typer.echo("")

    # Track total wall clock time
    import time
    start_time = time.perf_counter()

    # Scoring weights (tunable parameters)
    weights = {
        "bird_size": 0.25,    # Large birds are more visually impressive
        "sharpness": 0.30,    # Sharp focus important for quality
        "confidence": 0.25,   # Detection confidence
        "position": 0.20,     # Binary penalty for edge-clipped birds
    }

    # Extract and score
    from .detector import BirdDetector
    detector = BirdDetector(
        bird_confidence=bird_confidence,
    )

    try:
        scored_frames, timing_stats = extract_and_score_frames(
            input_dir=input_dir,
            detector=detector,
            weights=weights,
            limit=limit,
        )

        if not scored_frames:
            typer.echo("No frames found to score", err=True)
            raise typer.Exit(1)

        # Save top N frames
        typer.echo("Saving top frames...")
        saved_paths = save_top_frames(
            frames=scored_frames,
            input_dir=input_dir,
            output_dir=output_dir,
            top_n=top_n,
        )

        # Save metadata
        metadata_path = output_dir / "frame_scores.json"
        save_frame_metadata(
            frames=scored_frames[:top_n],
            timing_stats=timing_stats,
            output_path=metadata_path,
            config={"weights": weights, "top_n": top_n},
        )

        # Calculate total time
        elapsed_seconds = time.perf_counter() - start_time
        elapsed_formatted = format_duration(elapsed_seconds)

        # Output results
        typer.echo("")
        typer.echo("Results:")
        typer.echo(f"  Frames scored:    {len(scored_frames)}")
        typer.echo(f"  Top frames saved: {top_n}")
        typer.echo(f"  Output dir:       {output_dir}/")
        typer.echo(f"  Total time:       {elapsed_formatted}")
        typer.echo("")
        typer.echo("Timing per frame:")
        typer.echo(f"  Confidence:  {timing_stats['confidence_ms_per_frame']:.1f}ms")
        typer.echo(f"  Sharpness:   {timing_stats['sharpness_ms_per_frame']:.1f}ms")
        typer.echo(f"  Bird size:   {timing_stats['bird_size_ms_per_frame']:.1f}ms")
        typer.echo(f"  Position:    {timing_stats['position_ms_per_frame']:.1f}ms")
        typer.echo(f"  Total:       {timing_stats['total_ms_per_frame']:.1f}ms")

    except ValueError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)


@app.command()
def publish(
    input_dir: Path = typer.Argument(..., help="Directory containing has_birds/ (output from process/filter)"),
    config_file: Path = typer.Option("~/.birdbird/cloudflare.json", "--config", "-c", help="Cloudflare config file"),
    new_batch: bool = typer.Option(False, "--new-batch", "-n", help="Create new batch sequence (for additional footage same day)"),
) -> None:
    """Publish highlights and frames to Cloudflare R2.

    By default, replaces existing batch for the same date. Use --new-batch to create
    a new sequence (e.g., 20260114_02) when you collected additional footage same day.

    @author Claude Sonnet 4.5 Anthropic
    """
    import json

    # Expand ~ in config_file path
    config_file = Path(config_file).expanduser()

    # Validate input directory
    if not input_dir.is_dir():
        typer.echo(f"Error: {input_dir} is not a directory", err=True)
        raise typer.Exit(1)

    # Check config file exists
    if not config_file.exists():
        typer.echo(f"Error: Config file not found: {config_file}", err=True)
        typer.echo("", err=True)
        typer.echo("Create config file with:", err=True)
        typer.echo("  mkdir -p ~/.birdbird", err=True)
        typer.echo("  nano ~/.birdbird/cloudflare.json", err=True)
        typer.echo("", err=True)
        typer.echo("See README.md for setup instructions", err=True)
        raise typer.Exit(1)

    # Load config
    try:
        with open(config_file) as f:
            config = json.load(f)
    except json.JSONDecodeError as e:
        typer.echo(f"Error: Invalid JSON in config file: {e}", err=True)
        raise typer.Exit(1)

    # Validate required config keys
    required_keys = ['r2_access_key_id', 'r2_secret_access_key', 'r2_bucket_name', 'r2_account_id', 'r2_endpoint']
    missing_keys = [k for k in required_keys if k not in config]
    if missing_keys:
        typer.echo(f"Error: Missing required keys in config: {', '.join(missing_keys)}", err=True)
        raise typer.Exit(1)

    # Publish
    try:
        result = publish_to_r2(input_dir, config, create_new_batch=new_batch)

        typer.echo("")
        typer.echo("Success!")
        typer.echo(f"  Batch ID:    {result['batch_id']}")

        if result['batch_replaced']:
            typer.echo(f"  Re-used:     existing batch")

        typer.echo(f"  Uploaded:    {result['uploaded_files']} file(s)")
        if result['skipped_files'] > 0:
            typer.echo(f"  Skipped:     {result['skipped_files']} file(s) (unchanged)")

        typer.echo(f"  Clips:       {result['clip_count']}")
        typer.echo(f"  Duration:    {format_duration(result['highlights_duration'])}")

        if result['deleted_batches']:
            typer.echo(f"  Cleaned up:  {len(result['deleted_batches'])} old batch(es)")

        typer.echo("")
        typer.echo(f"View at: https://birdbird.rossarn.workers.dev/")

    except ValueError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)
    except Exception as e:
        typer.echo(f"Error publishing to R2: {e}", err=True)
        raise typer.Exit(1)


@app.command()
def songs(
    input_dir: Path = typer.Argument(..., help="Directory containing .avi clips"),
    output: Path = typer.Option(None, "--output", "-o", help="Output JSON path (default: input_dir/songs.json)"),
    song_confidence: float = typer.Option(0.5, "--song-conf", "-s", help="Min confidence for song detection (0.0-1.0)"),
    lat: float = typer.Option(None, "--lat", help="Latitude for species filtering (default: from config)"),
    lon: float = typer.Option(None, "--lon", help="Longitude for species filtering (default: from config)"),
    song_threads: int = typer.Option(2, "--song-threads", help="CPU threads for BirdNET"),
    limit: int | None = typer.Option(None, "--limit", "-l", help="Max clips to process (for testing)"),
    force: bool = typer.Option(False, "--force", "-f", help="Overwrite existing songs.json without prompting"),
) -> None:
    """Detect bird songs in clips using BirdNET.

    Extracts audio from AVI files and analyzes for bird vocalizations.
    Produces a JSON file listing all detections with species, confidence,
    and timestamps.

    Location can be set in ~/.birdbird/config.json or via --lat/--lon flags.

    @author Claude Opus 4.5 Anthropic
    """
    if not input_dir.is_dir():
        typer.echo(f"Error: {input_dir} is not a directory", err=True)
        raise typer.Exit(1)

    if output is None:
        output = input_dir / "songs.json"

    # Check if output file already exists
    if output.exists():
        if force:
            typer.echo(f"Removing existing {output}...")
            output.unlink()
            typer.echo("")
        else:
            typer.echo(f"Warning: {output} already exists")
            typer.echo("")
            typer.echo("Options:")
            typer.echo("  1. Remove and re-analyze (recommended)")
            typer.echo("  2. Cancel")
            typer.echo("")

            choice = typer.prompt("Choose option", type=int, default=1)

            if choice == 1:
                typer.echo(f"Removing {output}...")
                output.unlink()
                typer.echo("")
            else:
                typer.echo("Cancelled")
                raise typer.Exit(0)

    # Apply config defaults for location if not provided on CLI
    if lat is None and lon is None:
        config_lat, config_lon = get_location()
        if config_lat is not None and config_lon is not None:
            lat, lon = config_lat, config_lon

    # Validate location args (both or neither after config applied)
    if (lat is None) != (lon is None):
        typer.echo("Error: --lat and --lon must both be provided for location filtering", err=True)
        raise typer.Exit(1)

    # Count clips
    clips = sorted(input_dir.glob("*.avi"))
    clip_count = min(len(clips), limit) if limit else len(clips)

    typer.echo(f"Analyzing bird songs in {clip_count} clips from {input_dir}")
    typer.echo(f"Settings: song_conf={song_confidence}, song_threads={song_threads}")
    if lat is not None and lon is not None:
        # Check if location came from config (compare with config values)
        config_lat, config_lon = get_location()
        from_config = (lat == config_lat and lon == config_lon)
        source = " (from config)" if from_config else ""
        typer.echo(f"Location filter: lat={lat}, lon={lon}{source}")
    typer.echo("")

    import time
    start_time = time.perf_counter()

    try:
        results = analyze_songs(
            input_dir=input_dir,
            min_confidence=song_confidence,
            lat=lat,
            lon=lon,
            threads=song_threads,
            limit=limit,
        )

        # Save results
        save_song_detections(results, output)

        elapsed_seconds = time.perf_counter() - start_time

        typer.echo("")
        typer.echo("Results:")
        typer.echo(f"  Files processed:    {results['summary']['files_processed']}")
        typer.echo(f"  Files with songs:   {results['summary']['files_with_detections']}")
        typer.echo(f"  Total detections:   {results['summary']['total_detections']}")
        typer.echo(f"  Unique species:     {results['summary']['unique_species']}")
        typer.echo(f"  Processing time:    {format_duration(elapsed_seconds)}")
        typer.echo(f"  Output:             {output}")

        if results['summary']['species_list']:
            typer.echo("")
            typer.echo("Species detected:")
            for species in results['summary']['species_list'][:10]:  # Show top 10
                typer.echo(f"  - {species}")
            if len(results['summary']['species_list']) > 10:
                typer.echo(f"  ... and {len(results['summary']['species_list']) - 10} more")

    except ValueError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)
    except Exception as e:
        typer.echo(f"Error analyzing songs: {e}", err=True)
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
