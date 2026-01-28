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
- **birdnet-analyzer** (≥2.4.0) - Bird song detection from audio

## Quickstart

```bash
# Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install in development mode
pip install -e .

# Process clips: filter + highlights + frames + songs in one step
birdbird process /path/to/clips

# Test with limited clips first
birdbird process /path/to/clips --limit 10

# Or run steps separately:
birdbird filter /path/to/clips
birdbird highlights /path/to/clips/has_birds/
birdbird frames /path/to/clips/has_birds/ --top-n 20

# Detect bird songs from audio (standalone step)
birdbird songs /path/to/clips

# Optional: Publish to web (requires R2 setup - see below)
birdbird publish /path/to/clips
```

## Setup

### General Configuration

Create a config file at `~/.birdbird/config.json` for user-specific settings:

```bash
mkdir -p ~/.birdbird
nano ~/.birdbird/config.json
```

```json
{
  "location": {
    "lat": 51.35,
    "lon": -2.15
  }
}
```

**Supported settings:**

- `location.lat` / `location.lon` - Default coordinates for BirdNET species filtering in the `songs` command. Speeds up analysis by limiting to species found in your region. Can be overridden with `--lat`/`--lon` CLI flags.

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

7. **Configure CORS for R2 bucket** (required for web viewer):
   - In Cloudflare R2 dashboard, select your bucket
   - Go to Settings → CORS Policy
   - Add a CORS rule allowing your production domain and localhost for development:
     ```json
     [
       {
         "AllowedOrigins": [
           "https://your-production-domain.com",
           "http://localhost:3000"
         ],
         "AllowedMethods": ["GET"],
         "AllowedHeaders": ["*"],
         "ExposeHeaders": [],
         "MaxAgeSeconds": 3600
       }
     ]
     ```

8. **Set up the web viewer** (one-time):
   - Copy the viewer template to your website repo:
     ```bash
     cp src/birdbird/templates/viewer.html /path/to/your/website/index.html
     ```
   - Deploy to your web host (Cloudflare Pages, GitHub Pages, etc.)

   For local testing before deployment:
   ```bash
   npx serve -l 3000 src/birdbird/templates
   # Open http://localhost:3000/viewer.html
   ```

9. **Test publishing**:
   ```bash
   birdbird publish /path/to/clips
   ```

## Technical Overview

### Architecture

```
src/birdbird/
├── cli.py           # Typer CLI entry point
├── config.py        # User config loading (~/.birdbird/config.json)
├── detector.py      # BirdDetector class (YOLOv8-nano)
├── filter.py        # Batch filtering logic
├── frames.py        # Quality-based frame extraction and ranking
├── highlights.py    # Highlights reel generation
├── publish.py       # R2 upload with batch management
└── songs.py         # BirdNET audio analysis
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
- **Highlights**: MP4 reel concatenating bird activity segments
- **Frames**: Top-N JPEG frames ranked by multi-factor quality score (confidence, sharpness, bird size, position)
- **Songs**: JSON file with bird vocalizations detected by BirdNET (species, confidence, timestamps), plus normalized audio clips for each species

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

| #    | Milestone                  | Description                                                                                                      | Status |
| ---- | -------------------------- | ---------------------------------------------------------------------------------------------------------------- | ------ |
| M1   | Bird detection filter      | Discard clips without birds (eliminate wind false positives)                                                     | Done   |
| M2   | Highlights reel v1         | Concatenate segments with bird activity                                                                          | Done   |
| M2.1 | Highlights reel seek       | Based on M4 output, provide buttons to seek to timestamps with highest confidence for each species               |        |
| M2.2 | Publish highlights to web  | Upload to Cloudflare R2 with static web viewer showing video, frames, and audio stats                            | Done   |
| M3   | Highlight images           | Extract some nice-looking in-focus bird frames with timestamps                                                   | Done   |
| M3.1 | Highlight images v2        | Improve selection based on highest confidence frames for M4, and species variety.             | |
| M4   | Visual species detection   | Identify species, generate timeline summary with frame capture                                                   | Done   |
| M5   | Full report, stats         | Automated summary reports, expanding on M2.2 to showcase the M3/M4 material                                      |        |
| M6   | Best action sequence       | Curated "best action": algo to find best 30 second sequence based on max species variety and confidence and quantity.  Then expand on M2.1, button to seek to the start of that 30 seconds |        |
| M7   | Structured storage         | database backend to get stats/graphs on species counts, times usually seen, etc                                  |        |

## Other Feature Ideas

| #   | Feature                       | Description                                                                                                                                                                                                   | Status |
| --- | ----------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------ |
| F1  | Other objects                 | If other misc objects are detected with a separate confidence threshold, note those. Might get some squirrels, cats, etc.                                                                                     |        |
| F2  | Upload progress reporting     | Add progress bar/percentage for R2 uploads in publish command (especially for large video files)                                                                                                              | Done   |
| F3  | Corrupted input file handling | Improve detection and handling of corrupted MJPEG frames (camera recording issues, SD card errors). Could validate files before processing, skip severely corrupted clips, or log warnings for manual review. |        |
| F4  | Multiple bird detection       | Detect and count multiple birds in a single frame. Currently returns first detection only. Would enable richer captions (e.g., "2 Birds 85%, 72%"), social behavior tracking, and better statistics.          |        |
| F5  | Audio species detection       | Species detection from audio using BirdNET. Extracts normalized audio clips for each species and publishes to web viewer with playback.                                                                       | Done   |
| F6  | Credits page                  | Links to other projects/modules we are using, including licensing info                                                                                                                                        | Done   |
| F7  | Analytics                     | Add some lightweight analytics, for example Umami using Umami Cloud Free tier.                                                                                                                                |        |
| F8  | Staging                       | Add a staging target so viewer changes can be tested before going live                                                                                                                                        |        |
| F9  | Ongoing accessibility         | Add accessibility testing in local pipeline, pre-commit, perhaps using playwright                                                                                                                             |        |
| F10 | Add favicon | | |

## Input Format

- **Source**: Bird feeder camera with motion detection
- **Format**: AVI (MJPEG, 1440x1080, 30fps, ~10 seconds, ~27MB each)
- **Filename**: `DDHHmmss00.avi` (day + time; month/year from parent directory name)
- **Batches**: Downloaded every few days into dated directories (e.g., `20260114/`)
