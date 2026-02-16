#!/usr/bin/env python3
"""Update existing R2 batch metadata with start_date/end_date fields.

This script updates metadata.json files in R2 without re-uploading videos/frames.
"""

import json
import sys
from pathlib import Path

import typer

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from birdbird.publish import (
    create_r2_client,
    extract_date_range,
    extract_original_date,
    list_batches,
)


def load_config() -> dict:
    """Load cloud storage configuration (Cloudflare R2 or S3-compatible)."""
    config_path = Path.home() / ".birdbird" / "cloud-storage.json"
    if not config_path.exists():
        raise FileNotFoundError(f"Config not found: {config_path}")

    with open(config_path) as f:
        return json.load(f)


def find_local_batch_dir(batch_id: str, birds_dir: Path) -> Path | None:
    """Find local directory for a batch ID (e.g., 20260116_01 -> /BIRDS/20260116)."""
    # Extract date from batch ID (e.g., 20260116_01 -> 20260116)
    date_part = batch_id.split("_")[0]

    # Look for matching directory
    batch_dir = birds_dir / date_part
    if batch_dir.exists() and batch_dir.is_dir():
        return batch_dir

    return None


def update_batch_metadata(
    s3_client,
    bucket_name: str,
    batch_id: str,
    birds_dir: Path,
) -> bool:
    """Update metadata.json for a single batch with date range fields.

    Returns: True if updated, False if skipped
    """
    typer.echo(f"Processing batch: {batch_id}")

    # Download existing metadata
    try:
        response = s3_client.get_object(Bucket=bucket_name, Key=f"batches/{batch_id}/metadata.json")
        metadata = json.loads(response["Body"].read())
    except Exception as e:
        typer.echo(f"  ⚠ Could not download metadata: {e}", err=True)
        return False

    # Check if already has start_date/end_date
    if "start_date" in metadata and "end_date" in metadata:
        typer.echo("  ✓ Already has date range fields, skipping")
        return False

    # Find local batch directory
    local_batch_dir = find_local_batch_dir(batch_id, birds_dir)
    if not local_batch_dir:
        typer.echo("  ⚠ Local directory not found, skipping", err=True)
        return False

    has_birds_dir = local_batch_dir / "has_birds"
    if not has_birds_dir.exists():
        typer.echo(f"  ⚠ has_birds/ directory not found in {local_batch_dir}, skipping", err=True)
        return False

    # Extract original date and date range
    original_date = metadata.get("original_date")
    if not original_date:
        # Fallback: extract from directory name
        original_date = extract_original_date(local_batch_dir)

    start_date, end_date = extract_date_range(has_birds_dir, original_date)

    # Add new fields to metadata
    metadata["start_date"] = start_date
    metadata["end_date"] = end_date

    # Upload updated metadata
    try:
        s3_client.put_object(
            Bucket=bucket_name,
            Key=f"batches/{batch_id}/metadata.json",
            Body=json.dumps(metadata, indent=2),
            ContentType="application/json",
        )
        typer.echo(f"  ✓ Updated: {start_date} to {end_date}")
        return True
    except Exception as e:
        typer.echo(f"  ✗ Upload failed: {e}", err=True)
        return False


def update_latest_json(s3_client, bucket_name: str, updated_batches: set[str]):
    """Update latest.json with new metadata fields."""
    typer.echo("\nUpdating latest.json...")

    try:
        # Download latest.json
        response = s3_client.get_object(Bucket=bucket_name, Key="latest.json")
        latest_data = json.loads(response["Body"].read())

        # Update batches that were modified
        for batch_summary in latest_data.get("batches", []):
            batch_id = batch_summary["id"]

            if batch_id in updated_batches:
                # Fetch updated metadata
                try:
                    meta_response = s3_client.get_object(Bucket=bucket_name, Key=f"batches/{batch_id}/metadata.json")
                    metadata = json.loads(meta_response["Body"].read())

                    # Add start_date/end_date to batch summary
                    batch_summary["start_date"] = metadata.get("start_date")
                    batch_summary["end_date"] = metadata.get("end_date")

                except Exception as e:
                    typer.echo(f"  ⚠ Could not update {batch_id} in latest.json: {e}")

        # Upload updated latest.json
        s3_client.put_object(
            Bucket=bucket_name,
            Key="latest.json",
            Body=json.dumps(latest_data, indent=2),
            ContentType="application/json",
        )
        typer.echo("  ✓ latest.json updated")

    except Exception as e:
        typer.echo(f"  ✗ Failed to update latest.json: {e}", err=True)


def main(
    birds_dir: Path = typer.Argument(
        Path("/home/ross/BIRDS"), help="Path to BIRDS directory containing batch subdirectories"
    ),
):
    """Update all batch metadata files in R2 with start_date/end_date fields."""
    # Load config
    config = load_config()

    # Create R2 client
    typer.echo("Connecting to R2...")
    s3_client = create_r2_client(config)
    bucket_name = config["r2_bucket_name"]

    # List all batches
    batches = list_batches(s3_client, bucket_name)
    typer.echo(f"Found {len(batches)} batches in R2\n")

    if not batches:
        typer.echo("No batches found, exiting")
        return

    # Update each batch
    updated_batches = set()
    for batch_id in batches:
        if update_batch_metadata(s3_client, bucket_name, batch_id, birds_dir):
            updated_batches.add(batch_id)

    # Update latest.json if any batches were modified
    if updated_batches:
        typer.echo(f"\n{len(updated_batches)} batches updated")
        update_latest_json(s3_client, bucket_name, updated_batches)
    else:
        typer.echo("\nNo batches needed updating")


if __name__ == "__main__":
    typer.run(main)
