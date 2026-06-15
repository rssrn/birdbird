"""One-time migration: re-mux all R2 highlights.mp4 with -movflags +faststart.

Moves the MP4 moov atom to the front of each file so browsers can start
playback immediately without downloading the entire file first.

Original files are kept in ./faststart_originals/<batch_id>_highlights.mp4
for manual rollback if needed.

Usage:
    python scripts/migrate_faststart.py [--dry-run]

@author Claude Sonnet 4.6 Anthropic
"""

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from birdbird.publish import create_r2_client

CLOUD_STORAGE_CONFIG = Path.home() / ".birdbird" / "cloud-storage.json"
BACKUP_DIR = Path(__file__).parent / "faststart_originals"


def remux_with_faststart(input_path: Path, output_path: Path) -> bool:
    """Re-mux MP4 with moov atom at front. No re-encoding."""
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(input_path),
        "-c",
        "copy",
        "-movflags",
        "+faststart",
        "-loglevel",
        "error",
        str(output_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  ffmpeg error: {result.stderr.strip()}")
    return result.returncode == 0


def migrate(dry_run: bool = False) -> None:
    if not CLOUD_STORAGE_CONFIG.exists():
        print(f"Config not found: {CLOUD_STORAGE_CONFIG}")
        sys.exit(1)

    with open(CLOUD_STORAGE_CONFIG) as f:
        config = json.load(f)

    required = ["r2_endpoint", "r2_access_key_id", "r2_secret_access_key", "r2_bucket_name"]
    missing = [k for k in required if not config.get(k)]
    if missing:
        print(f"Missing config keys: {', '.join(missing)}")
        sys.exit(1)

    s3 = create_r2_client(config)
    bucket = config["r2_bucket_name"]

    # Discover all batches
    response = s3.list_objects_v2(Bucket=bucket, Prefix="batches/", Delimiter="/")
    batch_ids = [p["Prefix"].rstrip("/").split("/")[1] for p in response.get("CommonPrefixes", [])]

    if not batch_ids:
        print("No batches found in R2.")
        return

    print(f"Found {len(batch_ids)} batch(es): {', '.join(sorted(batch_ids))}")

    if not dry_run:
        BACKUP_DIR.mkdir(exist_ok=True)
        print(f"Originals will be saved to: {BACKUP_DIR}/\n")
    else:
        print("[DRY RUN] No files will be modified.\n")

    ok = 0
    failed = []

    for batch_id in sorted(batch_ids):
        key = f"batches/{batch_id}/highlights.mp4"
        print(f"[{batch_id}] {key}")

        if dry_run:
            print("  -> would download, remux, upload")
            ok += 1
            continue

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            original = tmp / "original.mp4"
            remuxed = tmp / "faststart.mp4"

            # Download
            print("  Downloading...", end=" ", flush=True)
            s3.download_file(bucket, key, str(original))
            size_mb = original.stat().st_size / 1_048_576
            print(f"{size_mb:.1f} MB")

            # Keep a local backup before overwriting
            backup_path = BACKUP_DIR / f"{batch_id}_highlights.mp4"
            if not backup_path.exists():
                import shutil

                shutil.copy2(original, backup_path)
                print(f"  Backed up to {backup_path.name}")
            else:
                print(f"  Backup already exists, skipping ({backup_path.name})")

            # Re-mux
            print("  Remuxing with faststart...", end=" ", flush=True)
            if not remux_with_faststart(original, remuxed):
                print("FAILED")
                failed.append(batch_id)
                continue
            new_size_mb = remuxed.stat().st_size / 1_048_576
            print(f"done ({new_size_mb:.1f} MB)")

            # Upload
            print("  Uploading...", end=" ", flush=True)
            s3.upload_file(
                str(remuxed),
                bucket,
                key,
                ExtraArgs={"ContentType": "video/mp4"},
            )
            print("done")

        ok += 1

    print(f"\nDone: {ok}/{len(batch_ids)} succeeded" + (f", {len(failed)} failed: {failed}" if failed else ""))
    if not dry_run and ok > 0:
        print(f"Originals saved in: {BACKUP_DIR}/")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true", help="List what would be done without making changes")
    args = parser.parse_args()
    migrate(dry_run=args.dry_run)
