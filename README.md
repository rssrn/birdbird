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

### Remote GPU (Optional - for Species Identification)

Species identification uses **BioCLIP** running on a remote GPU to avoid local system slowdown. The remote machine requires:

- **Python 3.10+** with BioCLIP environment
- **BioCLIP** - Vision-language model for bird species classification
- **SSH access** from your local machine
- **GPU** - CUDA-capable GPU recommended for faster processing

Note: BioCLIP is NOT installed locally - the `species` command transfers frames to the remote GPU for processing.

## Quickstart

```bash
# Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install in development mode
pip install -e .

# Process clips: filter + highlights + songs in one step
birdbird process /path/to/clips

# Test with limited clips first
birdbird process /path/to/clips --limit 10

# Or run steps separately:
birdbird filter /path/to/clips                    # 1. Filter clips with birds
birdbird highlights /path/to/clips/has_birds/     # 2. Generate highlights reel
birdbird species /path/to/clips                   # 3. Identify species (requires remote GPU)
birdbird songs /path/to/clips                     # 4. Detect bird songs from audio

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

### Remote GPU Configuration (Optional - for Species Identification)

To use the `species` command for visual species identification, configure a remote GPU:

1. **Set up remote machine** with BioCLIP:
   ```bash
   # On the remote machine
   python3 -m venv ~/bioclip_env
   source ~/bioclip_env/bin/activate
   pip install bioclip torch
   ```

2. **Configure SSH access** - Ensure passwordless SSH from your local machine:
   ```bash
   # On your local machine
   ssh-copy-id user@remote-hostname
   ssh user@remote-hostname  # Test connection
   ```

3. **Add remote config** to `~/.birdbird/config.json`:
   ```json
   {
     "location": {
       "lat": 51.35,
       "lon": -2.15
     },
     "species": {
       "processing": {
         "mode": "remote",
         "remote": {
           "host": "user@remote-hostname",
           "shell": "bash",
           "python_env": "~/bioclip_env"
         }
       },
       "min_confidence": 0.5,
       "samples_per_minute": 6.0,
       "labels_file": "~/.birdbird/bird_labels.txt"
     }
   }
   ```

4. **Create labels file** at `~/.birdbird/bird_labels.txt` with species to detect:
   ```
   Blue Tit
   Great Tit
   Robin
   Blackbird
   House Sparrow
   # Add more species...
   ```

**Note:** For WSL remote targets, use `"shell": "wsl"` instead of `"bash"`.

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
   - Copy the viewer templates to your website repo:
     ```bash
     cp src/birdbird/templates/*.html /path/to/your/website/
     cp src/birdbird/templates/*.css /path/to/your/website/
     cp src/birdbird/templates/*.js /path/to/your/website/
     cp src/birdbird/templates/*.png /path/to/your/website/
     cp src/birdbird/templates/*.ico /path/to/your/website/
     ```

   - **IMPORTANT: Configure the viewer** by editing `config.js`:
     ```bash
     nano /path/to/your/website/config.js
     ```

     Update these required values:
     ```javascript
     window.BIRDBIRD_CONFIG = {
       r2BaseUrl: 'https://pub-YOUR-BUCKET-ID.r2.dev',  // Your R2 public URL from step 6
       siteName: 'Bird Feeder Highlights',               // Your site name
       siteSubtitle: 'Your Location • Description',      // Your location and description
       analytics: ''                                      // Optional: analytics code snippet
     };
     ```

   - Deploy to your web host (Cloudflare Pages, GitHub Pages, etc.)

   For local testing before deployment:
   ```bash
   npx serve -l 3000 src/birdbird/templates
   # Open http://localhost:3000/index.html
   ```

   **Local Development Tip:** To avoid manually copying config changes during development iterations, create a `config.local.js` file in `src/birdbird/templates/` with your production values. This file is git-ignored and will be loaded preferentially by the viewer, allowing you to test directly from the templates directory without syncing to your website repo.

   ```bash
   # One-time setup for local development
   cp /path/to/your/website/config.js src/birdbird/templates/config.local.js
   ```

   **Note:** If you deploy without configuring `config.js`, a warning overlay will appear with instructions.

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
├── species.py       # BioCLIP species identification (remote GPU)
├── best_clips.py    # Best viewing windows for each species
├── songs.py         # BirdNET audio analysis
├── paths.py         # Path management utilities
├── publish.py       # R2 upload with batch management
└── templates/       # Web viewer HTML/CSS/JS
```

### Detection Approach

The pipeline uses a two-stage approach:

**Stage 1: Bird Detection (Filter)**
- Uses **YOLOv8-nano** pre-trained on [COCO](https://cocodataset.org/) (Common Objects in Context)
- Detects presence of birds (COCO class 14) with confidence threshold 0.2 (configurable via `--bird-conf`)
- Fast, lightweight detection to eliminate false positives (wind, shadows, etc.)
- Runs locally without GPU

**Stage 2: Species Identification (Species)**
- Uses **BioCLIP** (vision-language model) on remote GPU
- Samples frames from highlights video (default: 6 frames/minute)
- Classifies each frame against custom species labels
- Produces species.json with timestamps, confidence scores, and top predictions
- Requires remote GPU configuration (see Setup section)

### Frame Sampling Strategy

To balance speed and accuracy, frames are sampled with weighted density:

- **First second**: ~4 samples (every 0.25s) — captures the motion trigger event
- **Remaining duration**: 1 sample per second — catches birds that land after initial motion

This allows processing ~10s clips in ~2.3 seconds while catching brief bird appearances.

### Pipeline Flow

**Core Pipeline** (run together via `birdbird process` or individually):

1. **Filter** (`birdbird filter`) - Detect clips containing birds
   - Scans all AVI files in input directory
   - Uses YOLOv8-nano to detect birds in sampled frames
   - Copies clips with birds to `has_birds/` subdirectory
   - Saves `detections.json` with timestamps

2. **Highlights** (`birdbird highlights`) - Extract active segments
   - Uses detection timestamps from filter step
   - Binary search for segment start/end boundaries
   - Concatenates segments into `highlights.mp4`

3. **Songs** (`birdbird songs`) - Detect bird vocalizations
   - Extracts audio from AVI files to temporary WAV
   - Runs BirdNET-Analyzer for audio classification
   - Saves `songs.json` with all detections
   - Creates normalized audio clips per species

4. **Species** (`birdbird species`) - Identify species [Optional]
   - Samples frames from highlights video
   - Transfers frames to remote GPU via SSH
   - Runs BioCLIP inference with custom labels
   - Saves `species.json` and `best_clips.json`
   - Included in `process` if enabled in config or `--species` flag

**Publishing** (separate step):

5. **Publish** (`birdbird publish`) - Upload to web
   - Uploads highlights.mp4, species.json, songs.json to Cloudflare R2
   - Manages batch naming (YYYYMMDD-NN format)
   - Updates latest.json index for web viewer
   - Prompts before deleting old batches (>5)
   - Run separately after processing

### Output

The pipeline produces the following outputs in the input directory:

- **Filter** → `has_birds/` subdirectory + `detections.json`
  - Clips containing detected birds copied to `has_birds/`
  - Detection metadata with timestamps and confidence scores

- **Highlights** → `has_birds/highlights.mp4`
  - MP4 reel concatenating bird activity segments
  - Extracted using binary search on detection timestamps

- **Species** → `species.json` + `best_clips.json`
  - Species identifications with timestamps and confidence scores
  - Best viewing windows for each species (used by web viewer seek buttons)
  - Top 3 runner-up predictions for each detection

- **Songs** → `songs.json` + `normalized_audio/*.wav`
  - Bird vocalizations detected by BirdNET (species, confidence, timestamps)
  - Normalized audio clips for each detected species

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
| M2.1 | Highlights reel seek       | Based on M4 output, provide buttons to seek to timestamps with highest confidence for each species               | Done   |
| M2.2 | Publish highlights to web  | Upload to Cloudflare R2 with static web viewer showing video and audio stats                                     | Done   |
| M3   | Highlight images           | Extract species-specific frames from M4 detections                                                               |        |
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
