"""Publish highlights and frames to Cloudflare R2.

@author Claude Sonnet 4.5 Anthropic
"""

import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import boto3
import typer
from botocore.exceptions import ClientError
from tqdm import tqdm

from .filter import load_detections


def create_r2_client(config: dict):
    """Create boto3 S3 client configured for Cloudflare R2.

    @author Claude Sonnet 4.5 Anthropic
    """
    return boto3.client(
        's3',
        endpoint_url=config['r2_endpoint'],
        aws_access_key_id=config['r2_access_key_id'],
        aws_secret_access_key=config['r2_secret_access_key'],
        region_name='auto',  # R2 uses 'auto' for region
    )


def calculate_md5(file_path: Path) -> str:
    """Calculate MD5 hash of a file.

    @author Claude Sonnet 4.5 Anthropic
    """
    md5_hash = hashlib.md5()
    with open(file_path, 'rb') as f:
        # Read in 8KB chunks for efficiency
        for chunk in iter(lambda: f.read(8192), b''):
            md5_hash.update(chunk)
    return md5_hash.hexdigest()


def should_upload_file(s3_client, bucket_name: str, key: str, local_path: Path) -> bool:
    """Check if local file differs from R2 version.

    Compares local file MD5 with R2 object ETag (which is MD5 for single-part uploads).
    For multipart uploads (ETag contains '-'), compares file size as a heuristic.
    Returns True if file should be uploaded (different or doesn't exist).

    @author Claude Sonnet 4.5 Anthropic
    """
    try:
        # Get existing object metadata
        response = s3_client.head_object(Bucket=bucket_name, Key=key)
        remote_etag = response['ETag'].strip('"')  # Remove quotes from ETag
        remote_size = response['ContentLength']

        # Check if this is a multipart upload (ETag contains hyphen)
        if '-' in remote_etag:
            # For multipart uploads, ETag is not simple MD5
            # Use file size as heuristic (not perfect but fast and good enough)
            local_size = local_path.stat().st_size
            return local_size != remote_size  # Upload if sizes differ
        else:
            # Single-part upload - ETag is MD5, compare directly
            local_md5 = calculate_md5(local_path)
            return local_md5 != remote_etag  # Upload if different

    except ClientError as e:
        if e.response.get('Error', {}).get('Code') == '404':
            return True  # File doesn't exist, upload
        raise


def list_batches(s3_client, bucket_name: str) -> list[str]:
    """List all batch IDs from R2, sorted newest first.

    Returns: ["20220114_01", "20220113_01", ...]

    @author Claude Sonnet 4.5 Anthropic
    """
    try:
        # List all objects with 'batches/' prefix
        response = s3_client.list_objects_v2(
            Bucket=bucket_name,
            Prefix='batches/',
            Delimiter='/'
        )

        # Extract batch IDs from common prefixes (folder names)
        batch_ids = []
        if 'CommonPrefixes' in response:
            for prefix in response['CommonPrefixes']:
                # prefix['Prefix'] looks like 'batches/20220114_01/'
                path_parts = prefix['Prefix'].rstrip('/').split('/')
                if len(path_parts) == 2:
                    batch_ids.append(path_parts[1])

        # Sort descending (newest first) - lexicographic works for YYYYMMDD_NN
        batch_ids.sort(reverse=True)
        return batch_ids

    except ClientError as e:
        # If bucket is empty or prefix doesn't exist, return empty list
        if e.response.get('Error', {}).get('Code') == 'NoSuchKey':
            return []
        raise


def generate_batch_id(s3_client, bucket_name: str, original_date: str, create_new: bool = False) -> tuple[str, bool]:
    """Generate or reuse batch ID for original data date.

    Format: YYYYMMDD_NN where NN is sequence (01, 02, ...)
    Uses original data date (from folder name) for YYYYMMDD.

    Args:
        s3_client: Boto3 S3 client
        bucket_name: R2 bucket name
        original_date: Date string in "YYYY-MM-DD" format
        create_new: If True, create new sequence. If False (default), reuse existing or create _01.

    Returns:
        Tuple of (batch_id, batch_exists) where batch_exists indicates if this ID already exists in R2

    @author Claude Sonnet 4.5 Anthropic
    """
    # Convert original_date from "YYYY-MM-DD" or "unknown" to "YYYYMMDD"
    if original_date == "unknown":
        # Fallback to today's date if we couldn't parse the folder name
        date_prefix = datetime.now(timezone.utc).strftime('%Y%m%d')
    else:
        # Remove hyphens: "2022-01-14" -> "20220114"
        date_prefix = original_date.replace('-', '')

    # List existing batches with same date prefix
    all_batches = list_batches(s3_client, bucket_name)
    same_date_batches = [b for b in all_batches if b.startswith(date_prefix)]

    if not same_date_batches:
        # No existing batches for this date
        return f"{date_prefix}_01", False

    # Find max sequence number
    max_seq = 0
    for batch_id in same_date_batches:
        try:
            seq = int(batch_id.split('_')[1])
            max_seq = max(max_seq, seq)
        except (IndexError, ValueError):
            continue

    if create_new:
        # Create new sequence (for additional footage same day)
        next_seq = max_seq + 1
        return f"{date_prefix}_{next_seq:02d}", False
    else:
        # Reuse existing sequence (default: replace existing batch)
        return f"{date_prefix}_{max_seq:02d}", True


def get_highlights_duration(video_path: Path) -> float:
    """Get video duration using ffprobe.

    @author Claude Sonnet 4.5 Anthropic
    """
    cmd = [
        'ffprobe',
        '-v', 'error',
        '-show_entries', 'format=duration',
        '-of', 'default=noprint_wrappers=1:nokey=1',
        str(video_path)
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe failed: {result.stderr}")

    try:
        return float(result.stdout.strip())
    except ValueError:
        raise RuntimeError(f"Could not parse duration: {result.stdout}")


def extract_original_date(input_dir: Path) -> str:
    """Extract original date from directory name (e.g., /path/20220114 -> 2022-01-14).

    Falls back to "unknown" if cannot parse.

    @author Claude Sonnet 4.5 Anthropic
    """
    # Try to parse directory name as YYYYMMDD
    dir_name = input_dir.name

    if len(dir_name) == 8 and dir_name.isdigit():
        try:
            year = dir_name[0:4]
            month = dir_name[4:6]
            day = dir_name[6:8]
            # Validate it's a real date
            datetime.strptime(f"{year}-{month}-{day}", "%Y-%m-%d")
            return f"{year}-{month}-{day}"
        except ValueError:
            pass

    return "unknown"


def extract_date_range(has_birds_dir: Path, original_date: str) -> tuple[str, str]:
    """Extract date range from clip filenames with timestamp validation.

    Scans ALL clip filenames in the parent directory (not just has_birds) to determine
    the actual date range. Validates that the directory date falls within the filename
    date range as a sanity check (camera clock may be incorrect if device was reset).

    Args:
        has_birds_dir: Path to has_birds/ directory (parent dir will be scanned)
        original_date: Date from directory name (format "YYYY-MM-DD" or "unknown")

    Returns:
        Tuple of (start_date, end_date) as "YYYY-MM-DD" strings.
        If validation fails or cannot parse, returns (original_date, original_date).

    Examples:
        Valid timestamps:
        - Clips: 1411354000.avi, 1611595900.avi
        - Folder: 20260116
        - Directory day (16) is within filename range (14-16)
        - Returns: ("2026-01-14", "2026-01-16")

        Invalid timestamps (camera clock reset):
        - Clips: 0112345600.avi, 0323595900.avi
        - Folder: 20260119
        - Directory day (19) is NOT in filename range (1-3)
        - Returns: ("2026-01-19", "2026-01-19")

    @author Claude Sonnet 4.5 Anthropic
    """
    # If we couldn't parse the directory date, return single date
    if original_date == "unknown":
        return (original_date, original_date)

    # Parse directory date
    try:
        dir_date = datetime.strptime(original_date, "%Y-%m-%d")
        dir_day = dir_date.day
        year = dir_date.year
        month = dir_date.month
    except ValueError:
        return (original_date, original_date)

    # Scan all .avi files in PARENT directory (not just has_birds)
    # This gives us the full date range of the batch, even if some days had no birds
    parent_dir = has_birds_dir.parent
    avi_files = list(parent_dir.glob("*.avi"))
    if not avi_files:
        # No clips found, return single date
        return (original_date, original_date)

    # Extract days from filenames (format: DDHHmmss00.avi)
    filename_days = []
    for avi_path in avi_files:
        filename = avi_path.name
        if len(filename) >= 10 and filename[0:2].isdigit():
            try:
                day = int(filename[0:2])
                if 1 <= day <= 31:  # Basic sanity check
                    filename_days.append(day)
            except ValueError:
                continue

    if not filename_days:
        # Couldn't parse any filenames, return single date
        return (original_date, original_date)

    # Find min/max days from filenames
    min_day = min(filename_days)
    max_day = max(filename_days)

    # Validate: Check if directory day falls within filename day range
    # Handle month boundaries: if min_day > max_day, clips span month boundary
    # (e.g., days 30, 31, 01, 02 would have min_day=30, max_day=2)
    if min_day <= max_day:
        # Normal case: days within same month
        day_range_valid = min_day <= dir_day <= max_day
    else:
        # Month boundary case: check if dir_day is >= min_day (end of prev month)
        # or <= max_day (start of current month)
        day_range_valid = (dir_day >= min_day) or (dir_day <= max_day)

    # If validation fails, fall back to single directory date
    if not day_range_valid:
        return (original_date, original_date)

    # Validation passed - construct date range from filename days
    # Handle month boundary case
    if min_day > max_day:
        # Clips span month boundary (e.g., Dec 31 - Jan 2)
        # min_day is in previous month, max_day is in current month
        try:
            # Calculate previous month
            if month == 1:
                prev_month = 12
                prev_year = year - 1
            else:
                prev_month = month - 1
                prev_year = year

            start_date = datetime(prev_year, prev_month, min_day).strftime("%Y-%m-%d")
            end_date = datetime(year, month, max_day).strftime("%Y-%m-%d")
            return (start_date, end_date)
        except ValueError:
            # Invalid date construction, fall back
            return (original_date, original_date)
    else:
        # Normal case: all days within same month
        try:
            start_date = datetime(year, month, min_day).strftime("%Y-%m-%d")
            end_date = datetime(year, month, max_day).strftime("%Y-%m-%d")
            return (start_date, end_date)
        except ValueError:
            # Invalid date construction, fall back
            return (original_date, original_date)


def upload_batch(
    s3_client,
    bucket_name: str,
    batch_id: str,
    highlights_path: Path,
    frames_dir: Path,
    clip_count: int,
    original_date: str,
    has_birds_dir: Path,
    songs_path: Path | None = None,
    batch_exists: bool = False,
) -> dict:
    """Upload all batch assets to R2.

    When batch_exists=True, checks MD5/ETag before uploading each file to skip unchanged files.

    Returns: metadata dict for this batch

    @author Claude Sonnet 4.5 Anthropic
    """
    uploaded_files = []
    skipped_files = []
    # Extract date range from clip filenames with validation
    start_date, end_date = extract_date_range(has_birds_dir, original_date)

    # Read frame_scores.json to get top 3 frame info
    frame_scores_path = frames_dir / "frame_scores.json"
    with open(frame_scores_path) as f:
        frame_data = json.load(f)

    top_frames_data = frame_data['frames'][:3]

    # Get highlights duration
    highlights_duration = get_highlights_duration(highlights_path)

    # Upload timestamp
    uploaded_at = datetime.now(timezone.utc).isoformat()

    # Upload highlights.mp4 with progress bar
    highlights_key = f"batches/{batch_id}/highlights.mp4"
    file_size = highlights_path.stat().st_size

    if batch_exists and not should_upload_file(s3_client, bucket_name, highlights_key, highlights_path):
        typer.echo(f"  Skipping highlights.mp4 (unchanged, {file_size / (1024*1024):.1f} MB)")
        skipped_files.append('highlights.mp4')
    else:
        typer.echo(f"  Uploading highlights.mp4 ({file_size / (1024*1024):.1f} MB)...")

        with open(highlights_path, 'rb') as f:
            with tqdm(
                total=file_size,
                unit='B',
                unit_scale=True,
                unit_divisor=1024,
                desc="    Progress",
                leave=False
            ) as pbar:
                def upload_callback(bytes_amount):
                    pbar.update(bytes_amount)

                s3_client.upload_fileobj(
                    f,
                    bucket_name,
                    highlights_key,
                    ExtraArgs={'ContentType': 'video/mp4'},
                    Callback=upload_callback
                )
        uploaded_files.append('highlights.mp4')

    # Upload top 3 frames (rename to frame_01.jpg, frame_02.jpg, frame_03.jpg)
    typer.echo("  Checking top 3 frames...")
    top_frames_metadata = []

    for i, frame_info in enumerate(top_frames_data, start=1):
        # Find original frame file
        original_filename = frame_info['filename']
        original_path = frames_dir / original_filename

        if not original_path.exists():
            typer.echo(f"    Warning: Frame {original_filename} not found, skipping", err=True)
            continue

        # Upload as frame_01.jpg, frame_02.jpg, etc.
        new_filename = f"frame_{i:02d}.jpg"
        frame_key = f"batches/{batch_id}/{new_filename}"

        if batch_exists and not should_upload_file(s3_client, bucket_name, frame_key, original_path):
            typer.echo(f"    Skipping {new_filename} (unchanged)")
            skipped_files.append(new_filename)
        else:
            typer.echo(f"    Uploading {new_filename}")
            with open(original_path, 'rb') as f:
                s3_client.put_object(
                    Bucket=bucket_name,
                    Key=frame_key,
                    Body=f,
                    ContentType='image/jpeg'
                )
            uploaded_files.append(new_filename)

        top_frames_metadata.append({
            'filename': new_filename,
            'clip': frame_info['clip'],
            'timestamp': frame_info['timestamp'],
            'combined_score': frame_info['scores']['combined']
        })

    # Upload songs.json if available
    songs_summary = None
    if songs_path and songs_path.exists():
        songs_key = f"batches/{batch_id}/songs.json"

        with open(songs_path) as f:
            songs_data = json.load(f)

        if batch_exists and not should_upload_file(s3_client, bucket_name, songs_key, songs_path):
            typer.echo("  Skipping songs.json (unchanged)")
            skipped_files.append('songs.json')
        else:
            typer.echo("  Uploading songs.json...")
            # Upload full songs.json
            s3_client.put_object(
                Bucket=bucket_name,
                Key=songs_key,
                Body=json.dumps(songs_data, indent=2),
                ContentType='application/json'
            )
            uploaded_files.append('songs.json')

        # Create summary for metadata
        songs_summary = {
            'total_detections': songs_data['summary']['total_detections'],
            'unique_species': songs_data['summary']['unique_species'],
            'timestamps_reliable': songs_data.get('timestamps_reliable', True),
        }

    # Create metadata.json
    metadata = {
        'batch_id': batch_id,
        'uploaded': uploaded_at,
        'original_date': original_date,
        'start_date': start_date,
        'end_date': end_date,
        'clip_count': clip_count,
        'highlights_duration': round(highlights_duration, 2),
        'top_frames': top_frames_metadata
    }

    # Add songs summary if available
    if songs_summary:
        metadata['songs'] = songs_summary

    # Always upload metadata.json (it's tiny and includes current timestamp)
    typer.echo("  Uploading metadata.json...")
    s3_client.put_object(
        Bucket=bucket_name,
        Key=f"batches/{batch_id}/metadata.json",
        Body=json.dumps(metadata, indent=2),
        ContentType='application/json'
    )
    uploaded_files.append('metadata.json')

    # Add upload stats to metadata for reporting
    metadata['_upload_stats'] = {
        'uploaded': uploaded_files,
        'skipped': skipped_files,
    }

    return metadata


def update_latest_json(s3_client, bucket_name: str, batch_metadata: dict) -> None:
    """Update latest.json with new batch info.

    Fetches existing latest.json, prepends new batch, writes back.

    @author Claude Sonnet 4.5 Anthropic
    """
    # Try to fetch existing latest.json
    try:
        response = s3_client.get_object(
            Bucket=bucket_name,
            Key='latest.json'
        )
        latest_data = json.loads(response['Body'].read())
        batches = latest_data.get('batches', [])
    except ClientError as e:
        if e.response.get('Error', {}).get('Code') == 'NoSuchKey':
            # File doesn't exist yet, start fresh
            batches = []
        else:
            raise

    # Create batch summary for latest.json
    batch_summary = {
        'id': batch_metadata['batch_id'],
        'uploaded': batch_metadata['uploaded'],
        'original_date': batch_metadata['original_date'],
        'clip_count': batch_metadata['clip_count'],
        'highlights_duration': batch_metadata['highlights_duration']
    }

    # Remove all existing entries with this batch_id (handles duplicates from old bug)
    batches = [b for b in batches if b['id'] != batch_metadata['batch_id']]

    # Prepend batch (newest first)
    batches.insert(0, batch_summary)

    # Update latest.json
    latest_data = {
        'latest': batch_metadata['batch_id'],
        'batches': batches
    }

    typer.echo("  Updating latest.json...")
    s3_client.put_object(
        Bucket=bucket_name,
        Key='latest.json',
        Body=json.dumps(latest_data, indent=2),
        ContentType='application/json'
    )


def cleanup_old_batches(s3_client, bucket_name: str, keep_latest: int = 5) -> list[str]:
    """Prompt user and delete old batches if >keep_latest exist.

    Returns: list of deleted batch IDs

    @author Claude Sonnet 4.5 Anthropic
    """
    batches = list_batches(s3_client, bucket_name)

    if len(batches) <= keep_latest:
        return []

    # Batches to delete (oldest ones)
    to_delete = batches[keep_latest:]

    typer.echo("")
    typer.echo(f"Found {len(batches)} batches (keeping latest {keep_latest}):")
    for i, batch_id in enumerate(batches, 1):
        status = "KEEP" if i <= keep_latest else "DELETE"
        typer.echo(f"  {i}. {batch_id} - {status}")

    typer.echo("")
    confirm = typer.confirm(f"Delete {len(to_delete)} old batch(es)?", default=False)

    if not confirm:
        typer.echo("Skipping cleanup")
        return []

    deleted = []
    for batch_id in to_delete:
        typer.echo(f"  Deleting batch {batch_id}...")

        # List all objects in this batch
        response = s3_client.list_objects_v2(
            Bucket=bucket_name,
            Prefix=f"batches/{batch_id}/"
        )

        # Delete all objects
        if 'Contents' in response:
            for obj in response['Contents']:
                s3_client.delete_object(
                    Bucket=bucket_name,
                    Key=obj['Key']
                )

        deleted.append(batch_id)

    # Update latest.json to remove deleted batches
    try:
        response = s3_client.get_object(
            Bucket=bucket_name,
            Key='latest.json'
        )
        latest_data = json.loads(response['Body'].read())

        # Filter out deleted batches
        latest_data['batches'] = [
            b for b in latest_data['batches']
            if b['id'] not in deleted
        ]

        # Update latest pointer if it was deleted
        if latest_data['latest'] in deleted and latest_data['batches']:
            latest_data['latest'] = latest_data['batches'][0]['id']

        # Write back
        s3_client.put_object(
            Bucket=bucket_name,
            Key='latest.json',
            Body=json.dumps(latest_data, indent=2),
            ContentType='application/json'
        )
    except ClientError:
        pass  # latest.json might not exist yet

    return deleted


def publish_to_r2(
    input_dir: Path,
    config: dict,
    create_new_batch: bool = False,
) -> dict:
    """Main publish orchestration function.

    Args:
        input_dir: Directory containing has_birds/ subdirectory
        config: R2 configuration dict
        create_new_batch: If True, create new batch sequence. If False (default), replace existing.

    Returns: Publication summary dict

    @author Claude Sonnet 4.5 Anthropic
    """
    # Normalize path
    input_dir = Path(input_dir)

    # Handle case where user passed has_birds/ directly instead of parent
    if input_dir.name == "has_birds":
        # User passed has_birds/ directly, use parent directory
        input_dir = input_dir.parent
        typer.echo(f"Note: Using parent directory {input_dir}")
        typer.echo("")

    # Check for has_birds subdirectory
    has_birds_dir = input_dir / "has_birds"
    if not has_birds_dir.is_dir():
        raise ValueError(
            f"has_birds/ subdirectory not found in {input_dir}\n"
            f"       Run 'birdbird process' or 'birdbird filter' first to create has_birds/"
        )

    # Validate highlights.mp4 exists
    highlights_path = has_birds_dir / "highlights.mp4"
    if not highlights_path.exists():
        raise ValueError(
            f"highlights.mp4 not found in {has_birds_dir}\n"
            f"       Run 'birdbird highlights {has_birds_dir}' or 'birdbird process {input_dir}' first"
        )

    # Validate frames directory and files
    frames_dir = has_birds_dir / "frames"
    if not frames_dir.is_dir():
        raise ValueError(
            f"frames/ subdirectory not found in {has_birds_dir}\n"
            f"       Run 'birdbird frames {has_birds_dir}' first to extract frames"
        )

    frame_scores_path = frames_dir / "frame_scores.json"
    if not frame_scores_path.exists():
        raise ValueError(f"frame_scores.json not found in {frames_dir}")

    # Check we have at least 3 frames
    frame_files = sorted(frames_dir.glob("frame_*.jpg"))
    if len(frame_files) < 3:
        raise ValueError(f"Need at least 3 frames in {frames_dir}, found {len(frame_files)}")

    # Load detections to count clips
    detections = load_detections(has_birds_dir)
    clip_count = len(detections) if detections else 0

    # Check for songs.json (optional)
    songs_path = input_dir / "songs.json"
    if songs_path.exists():
        typer.echo(f"Found songs.json - will include in upload")
    else:
        typer.echo(f"No songs.json found - skipping (run 'birdbird songs {input_dir}' to add)")
        songs_path = None
    typer.echo("")

    # Extract original date from directory name
    original_date = extract_original_date(input_dir)

    # Create R2 client
    typer.echo("Connecting to R2...")
    s3_client = create_r2_client(config)
    bucket_name = config['r2_bucket_name']

    # Generate batch ID
    batch_id, batch_exists = generate_batch_id(s3_client, bucket_name, original_date, create_new=create_new_batch)

    if batch_exists and not create_new_batch:
        # Prompt user to confirm re-using existing batch
        typer.echo(f"Batch {batch_id} already exists")
        typer.echo("")
        typer.echo("Options:")
        typer.echo("  1. Re-use existing batch (update changed files only)")
        typer.echo("  2. Create new batch (additional footage from same day)")
        typer.echo("  3. Cancel")
        typer.echo("")

        choice = typer.prompt("Choose option", type=int, default=1)

        if choice == 1:
            typer.echo(f"Re-using batch: {batch_id}")
        elif choice == 2:
            # Regenerate batch_id with create_new=True
            batch_id, batch_exists = generate_batch_id(s3_client, bucket_name, original_date, create_new=True)
            typer.echo(f"Creating new batch: {batch_id}")
        else:
            typer.echo("Cancelled")
            raise typer.Exit(0)
    elif create_new_batch:
        typer.echo(f"Creating new batch: {batch_id}")
    else:
        typer.echo(f"Creating batch: {batch_id}")
    typer.echo("")

    # Upload batch
    typer.echo("Uploading assets to R2...")
    batch_metadata = upload_batch(
        s3_client=s3_client,
        bucket_name=bucket_name,
        batch_id=batch_id,
        highlights_path=highlights_path,
        frames_dir=frames_dir,
        clip_count=clip_count,
        original_date=original_date,
        has_birds_dir=has_birds_dir,
        songs_path=songs_path,
        batch_exists=batch_exists,
    )

    # Update latest.json
    update_latest_json(s3_client, bucket_name, batch_metadata)

    # Cleanup old batches
    deleted = cleanup_old_batches(s3_client, bucket_name, keep_latest=5)

    # Extract upload stats from metadata
    upload_stats = batch_metadata.pop('_upload_stats', {'uploaded': [], 'skipped': []})

    # Return summary
    return {
        'batch_id': batch_id,
        'uploaded_files': len(upload_stats['uploaded']),
        'skipped_files': len(upload_stats['skipped']),
        'uploaded_list': upload_stats['uploaded'],
        'skipped_list': upload_stats['skipped'],
        'clip_count': clip_count,
        'highlights_duration': batch_metadata['highlights_duration'],
        'deleted_batches': deleted,
        'batch_replaced': batch_exists and not create_new_batch,
    }
