"""Command-line interface.

@author Claude Opus 4.5 Anthropic
"""

import json
import shutil
from datetime import datetime
from pathlib import Path

import typer

from .config import get_location, get_species_config
from .filter import filter_clips
from .highlights import generate_highlights, get_video_duration
from .paths import BirdbirdPaths
from .publish import publish_to_r2, extract_date_range
from .songs import analyze_songs, save_song_detections
from .species import identify_species, save_species_results
from .best_clips import find_all_best_clips, save_best_clips

app = typer.Typer(help="Bird feeder video analysis pipeline")


def format_duration(seconds: float) -> str:
    """Format duration as MMm:SSs (e.g., '5m:23s' or '0m:45s').

    @author Claude Sonnet 4.5 Anthropic
    """
    minutes = int(seconds // 60)
    secs = int(seconds % 60)
    return f"{minutes}m:{secs:02d}s"


def write_local_metadata(paths: BirdbirdPaths, input_dir: Path) -> None:
    """Write metadata.json to assets directory after processing.

    Creates batch metadata similar to what publish command generates,
    but for local reference without uploading to R2.

    @author Claude Sonnet 4.5 Anthropic
    """
    # Extract date range (use same logic as publish)
    from .publish import extract_original_date
    original_date = extract_original_date(input_dir)
    start_date, end_date = extract_date_range(input_dir, original_date)

    # Read songs if available
    song_species = []
    if paths.songs_json.exists():
        with open(paths.songs_json) as f:
            songs_data = json.load(f)
            song_species = songs_data.get("summary", {}).get("species_list", [])

    # Count clips from detections
    clip_count = 0
    if paths.detections_json.exists():
        from .paths import load_detections
        detections = load_detections(paths.detections_json)
        clip_count = len(detections)

    # Build metadata
    metadata = {
        "batch_id": input_dir.name,  # Use directory name as ID
        "start_date": start_date,
        "end_date": end_date,
        "created_at": datetime.now().isoformat(),
        "clips": clip_count,
        "songs": {
            "species_count": len(song_species),
            "species_list": song_species,
        },
        "local": True,  # Marker that this is local, not published to R2
    }

    # Write to assets
    paths.ensure_assets_dirs()
    with open(paths.metadata_json, 'w') as f:
        json.dump(metadata, f, indent=2)


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
    paths = stats['paths']
    typer.echo(f"  Clips:          {paths.clips_dir}")
    typer.echo(f"  Detections:     {paths.detections_json}")


@app.command()
def highlights(
    input_dir: Path = typer.Argument(..., help="Directory containing original .avi clips"),
    output: Path = typer.Option(None, "--output", "-o", help="Output MP4 path (default: birdbird/assets/highlights.mp4)"),
    bird_confidence: float = typer.Option(0.2, "--bird-conf", "-b", help="Min confidence for bird detection"),
    buffer_before: float = typer.Option(1.0, "--buffer-before", help="Seconds before first bird detection"),
    buffer_after: float = typer.Option(1.0, "--buffer-after", help="Seconds after last bird detection (bird-free time)"),
    threads: int = typer.Option(2, "--threads", "-t", help="Max ffmpeg threads (default 2 for low-power systems)"),
    highest_quality: bool = typer.Option(False, "--highest-quality", help="Use highest quality (1440x1080 @ 30fps, larger file)"),
) -> None:
    """Generate a highlights reel from bird clips.

    By default, optimizes for web viewing (1440x1080 @ 24fps, smaller files).
    Use --highest-quality for maximum quality (30fps, larger files).

    Note: Run 'birdbird filter' first to detect and filter clips.
    """
    if not input_dir.is_dir():
        typer.echo(f"Error: {input_dir} is not a directory", err=True)
        raise typer.Exit(1)

    from .paths import BirdbirdPaths
    paths = BirdbirdPaths.from_input_dir(input_dir)

    # Check filtered clips exist
    if not paths.clips_dir.is_dir():
        typer.echo(f"Error: No filtered clips found. Run 'birdbird filter {input_dir}' first.", err=True)
        raise typer.Exit(1)

    if output is None:
        paths.ensure_assets_dirs()
        output = paths.highlights_mp4

    # Count clips and estimate duration (~7s per clip with binary search + extraction)
    clips = list(paths.clips_dir.glob("*.avi"))
    clip_count = len(clips)
    est_seconds = clip_count * 7
    est_minutes = est_seconds / 60

    quality_mode = "highest quality" if highest_quality else "web optimized"
    typer.echo(f"Generating highlights from {clip_count} clips (estimated {est_minutes:.1f} minutes)")
    typer.echo(f"Settings: bird_conf={bird_confidence}, buffer_before={buffer_before}s, buffer_after={buffer_after}s, threads={threads}, quality={quality_mode}")

    try:
        stats = generate_highlights(
            input_dir=paths.clips_dir,
            output_path=output,
            bird_confidence=bird_confidence,
            buffer_before=buffer_before,
            buffer_after=buffer_after,
            threads=threads,
            optimize_web=not highest_quality,
            paths=paths,
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
    lat: float = typer.Option(None, "--lat", help="Latitude for species filtering (default: from config)"),
    lon: float = typer.Option(None, "--lon", help="Longitude for species filtering (default: from config)"),
    limit: int | None = typer.Option(None, "--limit", "-l", help="Max clips to process (for testing)"),
    force: bool = typer.Option(False, "--force", "-f", help="Clear existing has_birds directory without prompting"),
    highest_quality: bool = typer.Option(False, "--highest-quality", help="Use highest quality (1440x1080 @ 30fps, larger file)"),
    no_song_clips: bool = typer.Option(False, "--no-song-clips", help="Skip extracting audio clips for each species"),
    run_species: bool = typer.Option(None, "--species/--no-species", help="Run visual species identification (default: from config)"),
) -> None:
    """Filter clips, generate highlights reel, analyze songs, and optionally identify species.

    By default, optimizes for web viewing (1440x1080 @ 24fps, smaller files).
    Use --highest-quality for maximum quality (30fps, larger files).
    """
    if not input_dir.is_dir():
        typer.echo(f"Error: {input_dir} is not a directory", err=True)
        raise typer.Exit(1)

    from .paths import BirdbirdPaths
    paths = BirdbirdPaths.from_input_dir(input_dir)

    # Apply config default for species if not specified on CLI
    if run_species is None:
        species_config = get_species_config()
        run_species = species_config.enabled

    # Estimate total time: ~2.3s filter + ~5s highlights per clip with birds (~30% detection rate)
    clips = sorted(input_dir.glob("*.avi"))
    clip_count = min(len(clips), limit) if limit else len(clips)
    est_bird_clips = int(clip_count * 0.3)  # Assume ~30% have birds
    est_seconds = clip_count * 2.3 + est_bird_clips * 5
    est_minutes = est_seconds / 60

    typer.echo(f"Processing {clip_count} clips (estimated {est_minutes:.1f} minutes total)")
    typer.echo(f"Settings: bird_conf={bird_confidence}")
    typer.echo("")

    # Check if birdbird directory already exists with content
    if paths.birdbird_dir.exists():
        # Check if there are any existing clips
        existing_clips = list(paths.clips_dir.glob("*.avi")) if paths.clips_dir.exists() else []
        if existing_clips:
            if force:
                typer.echo(f"Clearing existing {paths.birdbird_dir} ({len(existing_clips)} clips)...")
                shutil.rmtree(paths.birdbird_dir)
                typer.echo("")
            else:
                typer.echo(f"Warning: {paths.birdbird_dir} already exists with {len(existing_clips)} clips")
                typer.echo("This will mix old and new results, which may cause cache mismatches.")
                typer.echo("")
                typer.echo("Options:")
                typer.echo("  1. Clear and start fresh (recommended)")
                typer.echo("  2. Continue anyway (may have issues)")
                typer.echo("  3. Cancel")
                typer.echo("")

                choice = typer.prompt("Choose option", type=int, default=1)

                if choice == 1:
                    typer.echo(f"Removing {paths.birdbird_dir}...")
                    shutil.rmtree(paths.birdbird_dir)
                elif choice == 2:
                    typer.echo("Continuing with existing directory (results may be unpredictable)")
                else:
                    typer.echo("Cancelled")
                    raise typer.Exit(0)
                typer.echo("")

    # Ensure directories exist
    paths.ensure_working_dirs()
    paths.ensure_assets_dirs()

    # Calculate original duration before filtering
    typer.echo("Calculating original duration...")
    clips_to_process = clips[:clip_count]
    original_duration = sum(get_video_duration(c) for c in clips_to_process)
    typer.echo("")

    # Determine total steps
    total_steps = 4 if run_species else 3

    # Step 1: Filter
    typer.echo(f"Step 1/{total_steps}: Filtering clips...")
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
    typer.echo(f"Step 2/{total_steps}: Generating highlights...")

    if output is None:
        output = paths.highlights_mp4

    try:
        highlights_stats = generate_highlights(
            input_dir=paths.clips_dir,
            output_path=output,
            bird_confidence=bird_confidence,
            buffer_before=buffer_before,
            buffer_after=buffer_after,
            threads=threads,
            optimize_web=not highest_quality,
            original_duration=original_duration,
            paths=paths,
        )

        typer.echo("")
        typer.echo(f"  Duration:   {format_duration(highlights_stats.final_duration)} highlights from {format_duration(highlights_stats.bird_clips_duration)} filtered from {format_duration(original_duration)} original")
        typer.echo("")

    except (ValueError, RuntimeError) as e:
        typer.echo(f"Error generating highlights: {e}", err=True)
        raise typer.Exit(1)

    # Step 3: Analyze songs
    typer.echo(f"Step 3/{total_steps}: Analyzing bird songs...")

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
        # Remove existing songs.json if present
        if paths.songs_json.exists():
            paths.songs_json.unlink()

        try:
            songs_start = time.perf_counter()
            songs_results = analyze_songs(
                input_dir=input_dir,
                min_confidence=song_confidence,
                lat=lat,
                lon=lon,
                threads=song_threads,
                limit=limit,
                extract_clips=not no_song_clips,
                paths=paths,
            )

            # Save results
            save_song_detections(songs_results, paths.songs_json)

            songs_elapsed = time.perf_counter() - songs_start
            clips_msg = f", {songs_results['summary']['clips_extracted']} clips" if not no_song_clips else ""
            typer.echo(f"  Detected {songs_results['summary']['total_detections']} songs ({songs_results['summary']['unique_species']} species{clips_msg}) in {format_duration(songs_elapsed)}")
            typer.echo("")

        except Exception as e:
            typer.echo(f"  Error analyzing songs: {e}", err=True)
            typer.echo("  Continuing without songs data")
            typer.echo("")

    # Step 4: Species identification (optional)
    if run_species:
        typer.echo("Step 4/4: Identifying species (remote GPU)...")

        # Remove existing species.json if present
        if paths.species_json.exists():
            paths.species_json.unlink()

        def species_progress(msg: str) -> None:
            typer.echo(f"  {msg}")

        try:
            species_config = get_species_config()
            # Force remote mode
            species_config.processing_mode = "remote"

            species_results = identify_species(
                highlights_path=output,
                config=species_config,
                progress_callback=species_progress,
            )

            # Save results
            save_species_results(species_results, paths.species_json)

            typer.echo(f"  Identified {len(species_results.species_summary)} species in {species_results.processing_time_s:.1f}s")

            # Find best clips for each species (for M2.1 seek functionality)
            typer.echo("  Finding best clips for each species...")
            try:
                best_clips = find_all_best_clips(paths.species_json, window_duration_s=14.0)
                save_best_clips(best_clips, paths.best_clips_json, window_duration_s=14.0)
                typer.echo(f"  Found best clips for {len(best_clips)} species")
            except Exception as e:
                typer.echo(f"  Warning: Could not generate best clips: {e}")

            typer.echo("")

        except Exception as e:
            typer.echo(f"  Error identifying species: {e}", err=True)
            typer.echo("  Continuing without species data")
            typer.echo("")

    # Write local metadata.json
    write_local_metadata(paths, input_dir)

    typer.echo("Complete!")
    typer.echo(f"  Working:")
    typer.echo(f"    Clips:        {paths.clips_dir}/")
    typer.echo(f"    Detections:   {paths.detections_json}")
    typer.echo(f"  Assets:")
    typer.echo(f"    Highlights:   {paths.highlights_mp4}")
    if paths.songs_json.exists():
        typer.echo(f"    Songs:        {paths.songs_json}")
    if paths.song_clips_dir.exists() and list(paths.song_clips_dir.glob("*.wav")):
        typer.echo(f"    Song clips:   {paths.song_clips_dir}/")
    if paths.species_json.exists():
        typer.echo(f"    Species:      {paths.species_json}")
    if paths.best_clips_json.exists():
        typer.echo(f"    Best clips:   {paths.best_clips_json}")


@app.command(hidden=True)
def frames(
    input_dir: Path = typer.Argument(..., help="Directory containing original .avi clips"),
    top_n: int = typer.Option(20, "--top-n", "-n", help="Number of top frames to extract to candidates"),
    bird_confidence: float = typer.Option(0.2, "--bird-conf", "-b", help="Min confidence for bird detection"),
    limit: int | None = typer.Option(None, "--limit", "-l", help="Max clips to process (for testing)"),
    force: bool = typer.Option(False, "--force", "-f", help="Clear existing frames without prompting"),
) -> None:
    """Extract and rank best bird frames from filtered clips.

    Note: Run 'birdbird filter' first to detect and filter clips.
    This command is hidden as frame scoring is not part of the main pipeline.

    @author Claude Sonnet 4.5 Anthropic
    """
    if not input_dir.is_dir():
        typer.echo(f"Error: {input_dir} is not a directory", err=True)
        raise typer.Exit(1)

    from .paths import BirdbirdPaths, load_detections
    from .frames import copy_top_frames_to_assets
    paths = BirdbirdPaths.from_input_dir(input_dir)

    # Check filtered clips exist
    if not paths.clips_dir.is_dir():
        typer.echo(f"Error: No filtered clips found. Run 'birdbird filter {input_dir}' first.", err=True)
        raise typer.Exit(1)

    # Check for detections.json
    if not paths.detections_json.exists():
        typer.echo(f"Error: No detections.json found. Run 'birdbird filter {input_dir}' first.", err=True)
        raise typer.Exit(1)

    paths.ensure_working_dirs()
    paths.ensure_assets_dirs()

    # Check if frames directory already exists with content
    if paths.frames_candidates_dir.exists():
        existing_frames = list(paths.frames_candidates_dir.glob("frame_*.jpg"))
        if existing_frames:
            if force:
                typer.echo(f"Clearing existing frames from {paths.frames_candidates_dir} ({len(existing_frames)} frames)...")
                for frame_file in existing_frames:
                    frame_file.unlink()
                # Also remove metadata if it exists
                if paths.frame_scores_json.exists():
                    paths.frame_scores_json.unlink()
                typer.echo("")
            else:
                typer.echo(f"Warning: {paths.frames_candidates_dir} already exists with {len(existing_frames)} frames")
                typer.echo("")
                typer.echo("Options:")
                typer.echo("  1. Clear and re-extract (recommended)")
                typer.echo("  2. Continue anyway (may mix old and new frames)")
                typer.echo("  3. Cancel")
                typer.echo("")

                choice = typer.prompt("Choose option", type=int, default=1)

                if choice == 1:
                    typer.echo(f"Removing existing frames from {paths.frames_candidates_dir}...")
                    for frame_file in existing_frames:
                        frame_file.unlink()
                    if paths.frame_scores_json.exists():
                        paths.frame_scores_json.unlink()
                    typer.echo("")
                elif choice == 2:
                    typer.echo("Continuing with existing directory (results may be unpredictable)")
                    typer.echo("")
                else:
                    typer.echo("Cancelled")
                    raise typer.Exit(0)

    # Load and count detections
    detections = load_detections(paths.detections_json)
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
            paths=paths,
        )

        if not scored_frames:
            typer.echo("No frames found to score", err=True)
            raise typer.Exit(1)

        # Save top N frames to working directory
        typer.echo("Saving top frames to working directory...")
        saved_paths = save_top_frames(
            frames=scored_frames,
            clips_dir=paths.clips_dir,
            output_dir=paths.frames_candidates_dir,
            top_n=top_n,
        )

        # Save metadata
        save_frame_metadata(
            frames=scored_frames[:top_n],
            timing_stats=timing_stats,
            output_path=paths.frame_scores_json,
            config={"weights": weights, "top_n": top_n},
        )

        # Copy top 3 frames to assets directory
        typer.echo("Copying top 3 frames to assets...")
        asset_frames = copy_top_frames_to_assets(
            frame_scores_path=paths.frame_scores_json,
            candidates_dir=paths.frames_candidates_dir,
            assets_dir=paths.assets_dir,
            top_n=3,
        )

        # Calculate total time
        elapsed_seconds = time.perf_counter() - start_time
        elapsed_formatted = format_duration(elapsed_seconds)

        # Output results
        typer.echo("")
        typer.echo("Results:")
        typer.echo(f"  Frames scored:    {len(scored_frames)}")
        typer.echo(f"  Candidates:       {top_n} in {paths.frames_candidates_dir}/")
        typer.echo(f"  Assets:           3 in {paths.assets_dir}/")
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
    input_dir: Path = typer.Argument(..., help="Directory containing birdbird/assets/ (output from process)"),
    config_file: Path = typer.Option("~/.birdbird/cloudflare.json", "--config", "-c", help="Cloudflare config file"),
    new_batch: bool = typer.Option(False, "--new-batch", "-n", help="Create new batch sequence (for additional footage same day)"),
) -> None:
    """Publish highlights to Cloudflare R2.

    By default, replaces existing batch for the same date. Use --new-batch to create
    a new sequence (e.g., 20260114_02) when you collected additional footage same day.

    Note: Run 'birdbird process' first to generate assets for publishing.

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
    no_song_clips: bool = typer.Option(False, "--no-song-clips", help="Skip extracting audio clips for each species"),
) -> None:
    """Detect bird songs in clips using BirdNET.

    Extracts audio from AVI files and analyzes for bird vocalizations.
    Produces a JSON file listing all detections with species, confidence,
    and timestamps. Also extracts audio clips for the highest confidence
    detection of each species (use --no-song-clips to skip).

    Location can be set in ~/.birdbird/config.json or via --lat/--lon flags.

    @author Claude Opus 4.5 Anthropic
    """
    if not input_dir.is_dir():
        typer.echo(f"Error: {input_dir} is not a directory", err=True)
        raise typer.Exit(1)

    paths = BirdbirdPaths.from_input_dir(input_dir)
    paths.ensure_assets_dirs()

    if output is None:
        output = paths.songs_json

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
            extract_clips=not no_song_clips,
            paths=paths,
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
        if not no_song_clips:
            typer.echo(f"  Audio clips:        {results['summary']['clips_extracted']}")
        typer.echo(f"  Processing time:    {format_duration(elapsed_seconds)}")
        typer.echo(f"  Output:             {output}")
        if not no_song_clips and results['summary']['clips_extracted'] > 0:
            typer.echo(f"  Clips:              {paths.song_clips_dir}/")

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


@app.command()
def best_clips(
    input_dir: Path = typer.Argument(..., help="Directory containing species.json"),
    output: Path = typer.Option(None, "--output", "-o", help="Output JSON path (default: input_dir/birdbird/assets/best_clips.json)"),
    window_duration: float = typer.Option(14.0, "--window", "-w", help="Window duration in seconds (default: 14)"),
    force: bool = typer.Option(False, "--force", "-f", help="Overwrite existing best_clips.json without prompting"),
) -> None:
    """Find best time windows for each species from species.json.

    Analyzes species detections to find the highest-confidence time windows
    for each species. Output is used for seek functionality in the viewer.

    Note: Run 'birdbird species' first to generate species.json.

    @author Claude Sonnet 4.5 Anthropic
    """
    if not input_dir.is_dir():
        typer.echo(f"Error: {input_dir} is not a directory", err=True)
        raise typer.Exit(1)

    paths = BirdbirdPaths.from_input_dir(input_dir)

    # Check if species.json exists (try both locations for compatibility)
    species_json_path = None
    if paths.species_json.exists():
        species_json_path = paths.species_json
    elif (input_dir / "species.json").exists():
        species_json_path = input_dir / "species.json"

    if species_json_path is None:
        typer.echo(f"Error: species.json not found", err=True)
        typer.echo(f"  Checked: {paths.species_json}", err=True)
        typer.echo(f"  Checked: {input_dir / 'species.json'}", err=True)
        typer.echo("Run 'birdbird species' first to generate species data.", err=True)
        raise typer.Exit(1)

    if output is None:
        paths.ensure_assets_dirs()
        output = paths.best_clips_json

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
            typer.echo("  1. Remove and regenerate (recommended)")
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

    typer.echo(f"Finding best clips from {species_json_path}")
    typer.echo(f"Settings: window_duration={window_duration}s")
    typer.echo("")

    try:
        best_clips_data = find_all_best_clips(species_json_path, window_duration_s=window_duration)
        save_best_clips(best_clips_data, output, window_duration_s=window_duration)

        typer.echo("Results:")
        typer.echo(f"  Species analyzed:  {len(best_clips_data)}")
        typer.echo(f"  Window duration:   {window_duration}s")
        typer.echo(f"  Output:            {output}")

        if best_clips_data:
            typer.echo("")
            typer.echo("Best clips:")
            for species, clip in list(best_clips_data.items())[:10]:
                typer.echo(f"  {species}: {clip.start_s:.1f}s-{clip.end_s:.1f}s (score: {clip.score:.2f}, {clip.detection_count} detections)")
            if len(best_clips_data) > 10:
                typer.echo(f"  ... and {len(best_clips_data) - 10} more species")

    except FileNotFoundError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)
    except Exception as e:
        typer.echo(f"Error finding best clips: {e}", err=True)
        raise typer.Exit(1)


@app.command()
def species(
    input_dir: Path = typer.Argument(..., help="Directory containing has_birds/ with highlights.mp4"),
    output: Path = typer.Option(None, "--output", "-o", help="Output JSON path (default: input_dir/species.json)"),
    samples_per_minute: float = typer.Option(None, "--samples", "-s", help="Frames to sample per minute (default: from config or 6)"),
    min_confidence: float = typer.Option(None, "--min-conf", "-c", help="Min confidence threshold (default: from config or 0.5)"),
    mode: str = typer.Option(None, "--mode", "-m", help="Processing mode: remote (default from config)"),
    force: bool = typer.Option(False, "--force", "-f", help="Overwrite existing species.json without prompting"),
) -> None:
    """Identify bird species from highlights video using BioCLIP.

    Samples frames from highlights.mp4 and identifies species using BioCLIP
    on a remote GPU. Produces species.json with timestamps and detections.

    Requires remote GPU configuration in ~/.birdbird/config.json.

    @author Claude Opus 4.5 Anthropic
    """
    if not input_dir.is_dir():
        typer.echo(f"Error: {input_dir} is not a directory", err=True)
        raise typer.Exit(1)

    # Find highlights.mp4
    has_birds_dir = input_dir / "has_birds"
    highlights_path = has_birds_dir / "highlights.mp4"

    if not highlights_path.exists():
        # Also check input_dir directly
        highlights_path = input_dir / "highlights.mp4"
        if not highlights_path.exists():
            typer.echo(f"Error: highlights.mp4 not found in {has_birds_dir} or {input_dir}", err=True)
            typer.echo("Run 'birdbird process' first to generate highlights.", err=True)
            raise typer.Exit(1)

    if output is None:
        output = input_dir / "species.json"

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

    # Load config and apply CLI overrides
    config = get_species_config()

    if samples_per_minute is not None:
        config.samples_per_minute = samples_per_minute
    if min_confidence is not None:
        config.min_confidence = min_confidence
    if mode is not None:
        config.processing_mode = mode

    # Default to remote mode if not specified
    if config.processing_mode == "local":
        config.processing_mode = "remote"

    typer.echo(f"Identifying species from {highlights_path}")
    typer.echo(f"Settings: samples={config.samples_per_minute}/min, min_conf={config.min_confidence}, mode={config.processing_mode}")
    typer.echo("")

    def progress_callback(msg: str) -> None:
        typer.echo(f"  {msg}")

    try:
        results = identify_species(
            highlights_path=highlights_path,
            config=config,
            progress_callback=progress_callback,
        )

        # Save results
        save_species_results(results, output)

        typer.echo("")
        typer.echo("Results:")
        typer.echo(f"  Frames analyzed:    {results.total_frames}")
        typer.echo(f"  Video duration:     {format_duration(results.highlights_duration_s)}")
        typer.echo(f"  Processing time:    {results.processing_time_s:.1f}s")
        typer.echo(f"  Species detected:   {len(results.species_summary)}")
        typer.echo(f"  Output:             {output}")
        typer.echo("")
        typer.echo("Tip: Run 'birdbird best-clips' to find optimal time windows for each species")

        if results.species_summary:
            typer.echo("")
            typer.echo("Species breakdown:")
            for species_name, data in list(results.species_summary.items())[:10]:
                typer.echo(f"  {species_name}: {data['count']} ({data['avg_confidence']*100:.0f}% avg)")
            if len(results.species_summary) > 10:
                typer.echo(f"  ... and {len(results.species_summary) - 10} more species")

    except ValueError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)
    except RuntimeError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)
    except Exception as e:
        typer.echo(f"Error identifying species: {e}", err=True)
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
