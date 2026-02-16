#!/usr/bin/env python3
"""Remove a batch reference from latest.json in R2.

Use this after manually deleting batch files from R2 storage.
The script updates latest.json to remove the orphaned batch entry.

Usage:
    python remove_batch.py                    # interactive: list and pick
    python remove_batch.py 20260205_01        # remove specific batch
    python remove_batch.py 20260205_01 --dry-run  # preview without writing

@author Claude Sonnet 4.5 Anthropic
"""

import json
import sys
from pathlib import Path
from typing import Optional

import typer
from botocore.exceptions import ClientError

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from birdbird.publish import create_r2_client


def load_config() -> dict:
    """Load cloud storage configuration."""
    config_path = Path.home() / ".birdbird" / "cloud-storage.json"
    if not config_path.exists():
        raise FileNotFoundError(f"Config not found: {config_path}")
    with open(config_path) as f:
        return json.load(f)


def fetch_latest_json(s3_client, bucket_name: str) -> dict:
    """Download and parse latest.json from R2."""
    try:
        response = s3_client.get_object(Bucket=bucket_name, Key="latest.json")
        return json.loads(response["Body"].read())
    except ClientError as e:
        if e.response.get("Error", {}).get("Code") == "NoSuchKey":
            typer.echo("latest.json not found in R2.", err=True)
            raise typer.Exit(1)
        raise


def pick_batch_interactively(batches: list[dict]) -> str:
    """Show a numbered list of batches and prompt for selection."""
    typer.echo("\nBatches in latest.json:")
    for i, batch in enumerate(batches, 1):
        date_range = batch.get("start_date", batch.get("original_date", "?"))
        end = batch.get("end_date")
        if end and end != date_range:
            date_range = f"{date_range} – {end}"
        duration = batch.get("highlights_duration", 0)
        typer.echo(f"  {i}. {batch['id']}  ({date_range}, {duration:.0f}s)")

    typer.echo("")
    choice = typer.prompt("Enter number to remove", type=int)
    if not (1 <= choice <= len(batches)):
        typer.echo("Invalid choice.", err=True)
        raise typer.Exit(1)
    return batches[choice - 1]["id"]


def main(
    batch_id: Optional[str] = typer.Argument(
        None,
        help="Batch ID to remove (e.g. 20260205_01). Omit to pick interactively.",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Show what would change without writing to R2.",
    ),
) -> None:
    """Remove a batch entry from latest.json in R2.

    Use after manually deleting batch files from storage. Only updates the
    latest.json index; does not delete any objects from R2.

    @author Claude Sonnet 4.5 Anthropic
    """
    config = load_config()
    s3_client = create_r2_client(config)
    bucket_name = config["r2_bucket_name"]

    typer.echo("Fetching latest.json from R2...")
    latest_data = fetch_latest_json(s3_client, bucket_name)
    batches: list[dict] = latest_data.get("batches", [])
    current_latest: str = latest_data.get("latest", "")

    if not batches:
        typer.echo("No batches found in latest.json.")
        raise typer.Exit(0)

    # Determine which batch to remove
    if batch_id is None:
        batch_id = pick_batch_interactively(batches)

    # Validate it exists in latest.json
    existing_ids = [b["id"] for b in batches]
    if batch_id not in existing_ids:
        typer.echo(f"Batch '{batch_id}' not found in latest.json.", err=True)
        typer.echo(f"Known batches: {', '.join(existing_ids)}", err=True)
        raise typer.Exit(1)

    # Show what will change
    typer.echo(f"\nBatch to remove: {batch_id}")
    was_latest = current_latest == batch_id
    updated_batches = [b for b in batches if b["id"] != batch_id]
    new_latest = updated_batches[0]["id"] if updated_batches else None

    if was_latest:
        typer.echo(f"  'latest' pointer will change: {current_latest} → {new_latest or '(none)'}")
    typer.echo(f"  Remaining batches: {len(updated_batches)}")

    if dry_run:
        typer.echo("\n[dry-run] No changes written.")
        raise typer.Exit(0)

    typer.echo("")
    typer.confirm(f"Remove '{batch_id}' from latest.json?", abort=True)

    # Build updated latest.json
    updated_data: dict = {
        "latest": new_latest,
        "batches": updated_batches,
    }

    typer.echo("Uploading updated latest.json...")
    s3_client.put_object(
        Bucket=bucket_name,
        Key="latest.json",
        Body=json.dumps(updated_data, indent=2),
        ContentType="application/json",
    )

    typer.echo(f"Done. Removed '{batch_id}' from latest.json.")
    if was_latest and new_latest:
        typer.echo(f"'latest' now points to: {new_latest}")
    elif not updated_batches:
        typer.echo("Warning: no batches remain in latest.json.")


if __name__ == "__main__":
    typer.run(main)
