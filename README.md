# birdbird

Automated bird feeder video analysis pipeline. Processes motion-triggered clips from a bird feeder camera to identify bird species, generate highlight reels, and produce summary reports.

First used with a "Wilde & Oakes Bird Feeder with Smart Camera" set to capture 10-second clips.

## Dependencies

### System Requirements

- **Python 3.10+** - Core runtime
- **ffmpeg** - Video processing (segment extraction, concatenation, encoding)

  ```bash
  # Ubuntu/Debian
  sudo apt install ffmpeg

  # macOS
  brew install ffmpeg

  # Verify installation
  ffmpeg -version
  ```

### Python Packages

Installed automatically via `pip install -e .`:

- **ultralytics** (≥8.0.0) - YOLOv8 object detection model
- **opencv-python** (≥4.8.0) - Video/image processing
- **typer** (≥0.9.0) - CLI framework
- **tqdm** (≥4.66.0) - Progress bars
- **boto3** (≥1.42.0) - AWS/R2 SDK for cloud publishing (optional)

## Quickstart

```bash
# Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install in development mode
pip install -e .

# Process clips: filter + highlights + frames in one step
birdbird process /path/to/clips

# Test with limited clips first
birdbird process /path/to/clips --limit 10

# Or run steps separately:
birdbird filter /path/to/clips
birdbird highlights /path/to/clips/has_birds/
birdbird frames /path/to/clips/has_birds/ --top-n 20

# Optional: Publish to web (requires R2 setup - see below)
birdbird publish /path/to/clips
```

## Setup

### Cloudflare R2 Configuration (Optional - for Publishing)

To publish highlights to the web, configure Cloudflare R2:

1. **Create R2 bucket** in Cloudflare dashboard:

   - Navigate to R2 in left sidebar
   - Click "Create bucket"
   - Name it `birdbird-highlights`

2. **Generate R2 API token**:

   - In R2 section, click "Manage R2 API Tokens"
   - Click "Create API Token"
   - Name: `birdbird-upload`
   - Permissions: Object Read & Write for your bucket
   - Save the Access Key ID and Secret Access Key (you won't see the secret again!)

3. **Find your Account ID**:

   - Visible in R2 dashboard sidebar or in the URL

4. **Create config file**:

   ```bash
   mkdir -p ~/.birdbird
   nano ~/.birdbird/cloudflare.json
   ```

   Paste and fill in your values:

   ```json
   {
     "r2_access_key_id": "YOUR_ACCESS_KEY_ID",
     "r2_secret_access_key": "YOUR_SECRET_ACCESS_KEY",
     "r2_bucket_name": "birdbird-highlights",
     "r2_account_id": "YOUR_ACCOUNT_ID",
     "r2_endpoint": "https://YOUR_ACCOUNT_ID.r2.cloudflarestorage.com"
   }
   ```

5. **Secure the file**:

   ```bash
   chmod 600 ~/.birdbird/cloudflare.json
   ```

6. **Configure R2 bucket for public access**:

   - In Cloudflare R2 dashboard, select your bucket
   - Go to Settings → Public Access
   - Enable "Allow Access" and note the public R2.dev URL (e.g., `https://pub-xxxxx.r2.dev`)
   - This URL will be used in the viewer HTML

7. **Set up the web viewer** (one-time):

   - Copy the viewer template to your website repo:
     ```bash
     cp src/birdbird/templates/viewer.html /path/to/your/website/index.html
     ```
   - Edit `index.html` and replace `YOUR_R2_PUBLIC_URL_HERE` with your R2 public URL
   - Deploy to your web host (Cloudflare Pages, GitHub Pages, etc.)

8. **Test publishing**:
   ```bash
   birdbird publish /path/to/clips
   ```

## Technical Overview

### Architecture

```
src/birdbird/
├── cli.py           # Typer CLI entry point
├── detector.py      # BirdDetector class (YOLOv8-nano)
├── filter.py        # Batch filtering logic
├── highlights.py    # Highlights reel generation
└── frames.py        # Quality-based frame extraction and ranking
```

### Detection Approach

Uses **YOLOv8-nano** pre-trained on [COCO](https://cocodataset.org/) (Common Objects in Context), a dataset with 80 object categories including birds. This allows detection without custom training:

- **Bird detection**: COCO class 14 (bird) with default confidence threshold 0.2 (configurable via `--bird-conf`)

### Frame Sampling Strategy

To balance speed and accuracy, frames are sampled with weighted density:

- **First second**: ~4 samples (every 0.25s) — captures the motion trigger event
- **Remaining duration**: 1 sample per second — catches birds that land after initial motion

This allows processing ~10s clips in ~2.3 seconds while catching brief bird appearances.

### Output

- **Filter**: Clips containing detected birds are copied to a `has_birds/` subdirectory
- **Highlights**: MP4 reel concatenating bird activity segments with crossfade transitions
- **Frames**: Top-N JPEG frames ranked by multi-factor quality score (confidence, sharpness, bird size, position)

## Problem

A bird feeder camera captures 10-second AVI clips on motion detection, but:

- High false-positive rate (wind triggers recording)
- No species identification
- Manual review of hundreds of clips is impractical

## Goals

- Filter clips to those containing actual bird activity
- Identify bird species with timestamps
- Extract best in-focus frames
- Generate highlight reels of interesting footage
- Produce summary reports (email, eventually database)

## Milestones

| #    | Milestone                                                                                                             | Description                                                                                                      | Status |
| ---- | --------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------- | ------ |
| M1   | Bird detection filter                                                                                                 | Discard clips without birds (eliminate wind false positives)                                                     | Done   |
| M2   | Highlights reel v1                                                                                                    | Concatenate segments with bird activity with crossfade transitions                                               | Done   |
| M2.1 | Highlights reel captions                                                                                              | Add match type (e.g. bird or human) with confidence level within highlights reel, adjacent to existing timestamp |
| M2.2 | Publish highlights reel to web - maybe using cloudflare R2 for the blob and static cloudflare worker page to frame it |
| M3   | Highlight images                                                                                                      | Extract some nice-looking in-focus bird frames with timestamps                                                   | Done   |
| M4   | Visual species detection                                                                                              | Identify species, generate timeline summary with frame captures                                                  |        |
| M5   | Email or static web report                                                                                            | Automated summary reports, expanding on M2.2 to showcase the M3/M4 material                                      |        |
| M6   | Highlights reel v2                                                                                                    | Curated "best action" clips                                                                                      |        |
| M7   | Structured storage                                                                                                    | database backend to get stats/graphs on species counts, times usually seen, etc                                  |        |

## Other Feature Ideas

| #   | Feature                       | Description                                                                                                                                                                                                   |
| --- | ----------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| F1  | Other objects                 | If other misc objects are detected with a separate confidence threshold, note those. Might get some squirrels, cats, etc.                                                                                     |
| F2  | Upload progress reporting     | Add progress bar/percentage for R2 uploads in publish command (especially for large video files)                                                                                                              |
| F3  | Corrupted input file handling | Improve detection and handling of corrupted MJPEG frames (camera recording issues, SD card errors). Could validate files before processing, skip severely corrupted clips, or log warnings for manual review. |
| F4  | Multiple bird detection       | Detect and count multiple birds in a single frame. Currently returns first detection only. Would enable richer captions (e.g., "2 Birds 85%, 72%"), social behavior tracking, and better statistics.          |
| F5  | Audio species detection       | Add species detection from audio track, probably using BirdNet.  Perhaps publish selected audio clips.                                                                                                                                             |
| F6  | Credits page                  | Links to other projects/modules we are using, including licensing info                                                                                                                                        |

## Input Format

- **Source**: Bird feeder camera with motion detection
- **Format**: AVI (MJPEG, 1440x1080, 30fps, ~10 seconds, ~27MB each)
- **Filename**: `MMDDHHmmss.avi` (timestamp when clip was captured)
- **Batches**: Downloaded every few days into dated directories (e.g., `20260114/`)
