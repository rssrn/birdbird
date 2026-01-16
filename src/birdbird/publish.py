"""Publish highlights and frames to Cloudflare R2.

@author Claude Sonnet 4.5 Anthropic
"""

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


def list_batches(s3_client, bucket_name: str) -> list[str]:
    """List all batch IDs from R2, sorted newest first.

    Returns: ["20250115-01", "20250114-01", ...]

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
                # prefix['Prefix'] looks like 'batches/20250115-01/'
                path_parts = prefix['Prefix'].rstrip('/').split('/')
                if len(path_parts) == 2:
                    batch_ids.append(path_parts[1])

        # Sort descending (newest first) - lexicographic works for YYYYMMDD-NN
        batch_ids.sort(reverse=True)
        return batch_ids

    except ClientError as e:
        # If bucket is empty or prefix doesn't exist, return empty list
        if e.response.get('Error', {}).get('Code') == 'NoSuchKey':
            return []
        raise


def generate_batch_id(s3_client, bucket_name: str, original_date: str) -> str:
    """Generate next batch ID for upload date.

    Format: YYYYMMDD-NN where NN is sequence (01, 02, ...)
    Uses today's date for YYYYMMDD, increments NN if multiple uploads same day.

    @author Claude Sonnet 4.5 Anthropic
    """
    # Get today's date in YYYYMMDD format
    today = datetime.now(timezone.utc).strftime('%Y%m%d')

    # List existing batches with same date prefix
    all_batches = list_batches(s3_client, bucket_name)
    same_day_batches = [b for b in all_batches if b.startswith(today)]

    if not same_day_batches:
        return f"{today}-01"

    # Find max sequence number
    max_seq = 0
    for batch_id in same_day_batches:
        try:
            seq = int(batch_id.split('-')[1])
            max_seq = max(max_seq, seq)
        except (IndexError, ValueError):
            continue

    # Increment sequence
    next_seq = max_seq + 1
    return f"{today}-{next_seq:02d}"


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


def upload_batch(
    s3_client,
    bucket_name: str,
    batch_id: str,
    highlights_path: Path,
    frames_dir: Path,
    clip_count: int,
    original_date: str,
) -> dict:
    """Upload all batch assets to R2.

    Returns: metadata dict for this batch

    @author Claude Sonnet 4.5 Anthropic
    """
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
    file_size = highlights_path.stat().st_size
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
                f"batches/{batch_id}/highlights.mp4",
                ExtraArgs={'ContentType': 'video/mp4'},
                Callback=upload_callback
            )

    # Upload top 3 frames (rename to frame_01.jpg, frame_02.jpg, frame_03.jpg)
    typer.echo("  Uploading top 3 frames...")
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
        with open(original_path, 'rb') as f:
            s3_client.put_object(
                Bucket=bucket_name,
                Key=f"batches/{batch_id}/{new_filename}",
                Body=f,
                ContentType='image/jpeg'
            )

        top_frames_metadata.append({
            'filename': new_filename,
            'clip': frame_info['clip'],
            'timestamp': frame_info['timestamp'],
            'combined_score': frame_info['scores']['combined']
        })

    # Create metadata.json
    metadata = {
        'batch_id': batch_id,
        'uploaded': uploaded_at,
        'original_date': original_date,
        'clip_count': clip_count,
        'highlights_duration': round(highlights_duration, 2),
        'top_frames': top_frames_metadata
    }

    # Upload metadata.json
    typer.echo("  Uploading metadata.json...")
    s3_client.put_object(
        Bucket=bucket_name,
        Key=f"batches/{batch_id}/metadata.json",
        Body=json.dumps(metadata, indent=2),
        ContentType='application/json'
    )

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

    # Prepend new batch (newest first)
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
) -> dict:
    """Main publish orchestration function.

    Returns: Publication summary dict

    @author Claude Sonnet 4.5 Anthropic
    """
    # Normalize path
    input_dir = Path(input_dir)

    # Check for has_birds subdirectory
    has_birds_dir = input_dir / "has_birds"
    if not has_birds_dir.is_dir():
        raise ValueError(f"has_birds/ subdirectory not found in {input_dir}")

    # Validate highlights.mp4 exists
    highlights_path = has_birds_dir / "highlights.mp4"
    if not highlights_path.exists():
        raise ValueError(f"highlights.mp4 not found in {has_birds_dir}")

    # Validate frames directory and files
    frames_dir = has_birds_dir / "frames"
    if not frames_dir.is_dir():
        raise ValueError(f"frames/ subdirectory not found in {has_birds_dir}")

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

    # Extract original date from directory name
    original_date = extract_original_date(input_dir)

    # Create R2 client
    typer.echo("Connecting to R2...")
    s3_client = create_r2_client(config)
    bucket_name = config['r2_bucket_name']

    # Generate batch ID
    batch_id = generate_batch_id(s3_client, bucket_name, original_date)
    typer.echo(f"Publishing batch: {batch_id}")
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
    )

    # Update latest.json
    update_latest_json(s3_client, bucket_name, batch_metadata)

    # Cleanup old batches
    deleted = cleanup_old_batches(s3_client, bucket_name, keep_latest=5)

    # Return summary
    return {
        'batch_id': batch_id,
        'uploaded_files': 5,  # highlights.mp4 + 3 frames + metadata.json
        'clip_count': clip_count,
        'highlights_duration': batch_metadata['highlights_duration'],
        'deleted_batches': deleted,
    }
