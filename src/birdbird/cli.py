"""Command-line interface.

@author Claude Opus 4.5 Anthropic
"""

from pathlib import Path

import typer

from .filter import filter_clips
from .highlights import generate_highlights

app = typer.Typer(help="Bird feeder video analysis pipeline")


@app.command()
def filter(
    input_dir: Path = typer.Argument(..., help="Directory containing .avi clips"),
    bird_confidence: float = typer.Option(0.2, "--bird-conf", "-b", help="Min confidence for bird detection"),
    person_confidence: float = typer.Option(0.3, "--person-conf", "-p", help="Min confidence for person detection (close-up birds)"),
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
    typer.echo(f"Settings: bird_conf={bird_confidence}, person_conf={person_confidence}")

    stats = filter_clips(
        input_dir,
        bird_confidence=bird_confidence,
        person_confidence=person_confidence,
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
    person_confidence: float = typer.Option(0.3, "--person-conf", "-p", help="Min confidence for person detection"),
    buffer_before: float = typer.Option(1.0, "--buffer-before", help="Seconds before first bird detection"),
    buffer_after: float = typer.Option(1.0, "--buffer-after", help="Seconds after last bird detection (bird-free time)"),
    crossfade: float = typer.Option(0.5, "--crossfade", "-x", help="Crossfade transition duration in seconds"),
) -> None:
    """Generate a highlights reel from bird clips."""
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

    typer.echo(f"Generating highlights from {clip_count} clips (estimated {est_minutes:.1f} minutes)")
    typer.echo(f"Settings: bird_conf={bird_confidence}, person_conf={person_confidence}, buffer_before={buffer_before}s, buffer_after={buffer_after}s, crossfade={crossfade}s")

    try:
        stats = generate_highlights(
            input_dir=input_dir,
            output_path=output,
            bird_confidence=bird_confidence,
            person_confidence=person_confidence,
            buffer_before=buffer_before,
            buffer_after=buffer_after,
            crossfade_duration=crossfade,
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
    person_confidence: float = typer.Option(0.3, "--person-conf", "-p", help="Min confidence for person detection"),
    buffer_before: float = typer.Option(1.0, "--buffer-before", help="Seconds before first bird detection"),
    buffer_after: float = typer.Option(1.0, "--buffer-after", help="Seconds after last bird detection"),
    crossfade: float = typer.Option(0.5, "--crossfade", "-x", help="Crossfade transition duration"),
    limit: int | None = typer.Option(None, "--limit", "-l", help="Max clips to process (for testing)"),
) -> None:
    """Filter clips and generate highlights reel in one step."""
    if not input_dir.is_dir():
        typer.echo(f"Error: {input_dir} is not a directory", err=True)
        raise typer.Exit(1)

    # Estimate total time: ~2.3s filter + ~5s highlights per clip with birds (~30% detection rate)
    clips = sorted(input_dir.glob("*.avi"))
    clip_count = min(len(clips), limit) if limit else len(clips)
    est_bird_clips = int(clip_count * 0.3)  # Assume ~30% have birds
    est_seconds = clip_count * 2.3 + est_bird_clips * 5
    est_minutes = est_seconds / 60

    typer.echo(f"Processing {clip_count} clips (estimated {est_minutes:.1f} minutes total)")
    typer.echo(f"Settings: bird_conf={bird_confidence}, person_conf={person_confidence}")
    typer.echo("")

    # Step 1: Filter
    typer.echo("Step 1/2: Filtering clips...")
    filter_stats = filter_clips(
        input_dir,
        bird_confidence=bird_confidence,
        person_confidence=person_confidence,
        limit=limit,
    )

    pct = 100 * filter_stats['with_birds'] / filter_stats['total'] if filter_stats['total'] > 0 else 0
    typer.echo(f"  Found {filter_stats['with_birds']}/{filter_stats['total']} clips with birds ({pct:.1f}%)")
    typer.echo("")

    if filter_stats['with_birds'] == 0:
        typer.echo("No birds detected - skipping highlights generation")
        raise typer.Exit(0)

    # Step 2: Highlights
    typer.echo("Step 2/2: Generating highlights...")
    has_birds_dir = input_dir / "has_birds"

    if output is None:
        output = has_birds_dir / "highlights.mp4"

    try:
        highlights_stats = generate_highlights(
            input_dir=has_birds_dir,
            output_path=output,
            bird_confidence=bird_confidence,
            person_confidence=person_confidence,
            buffer_before=buffer_before,
            buffer_after=buffer_after,
            crossfade_duration=crossfade,
        )

        typer.echo("")
        typer.echo("Complete!")
        typer.echo(f"  Bird clips: {has_birds_dir}/")
        typer.echo(f"  Highlights: {output}")
        typer.echo(f"  Duration:   {highlights_stats.final_duration:.0f}s from {highlights_stats.original_duration:.0f}s original")

    except (ValueError, RuntimeError) as e:
        typer.echo(f"Error generating highlights: {e}", err=True)
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
