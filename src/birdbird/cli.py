"""Command-line interface.

@author Claude Opus 4.5 Anthropic
"""

from pathlib import Path

import typer

from .filter import filter_clips

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

    typer.echo(f"Processing clips in {input_dir}")
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


if __name__ == "__main__":
    app()
