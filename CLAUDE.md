# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

birdbird - Bird feeder video analysis pipeline. See README.md for full project description and milestones.

## Input Data

- Sample batch: `/home/ross/BIRDS/20260114/` (498 clips)
- Format: AVI (MJPEG 1440x1080 30fps), ~10s duration, ~27MB each
- Filename convention: `DDHHmmss00.avi` (day + time; month/year from parent directory name)
- **Note**: Camera timestamps may be incorrect if device clock was reset; treat directory name as source of truth

## Development Commands

**IMPORTANT**: This project REQUIRES venv setup and installation before running commands.

```bash
# REQUIRED SETUP (run once):
python3 -m venv .venv
source .venv/bin/activate  # On Linux/Mac
# .venv\Scripts\activate   # On Windows
pip install -e .

# Running commands:
# Option 1: Activate venv first, then run commands directly
source .venv/bin/activate
birdbird filter /path/to/clips

# Option 2: Prefix commands with .venv/bin/ (without activating)
.venv/bin/birdbird filter /path/to/clips

# NEVER use: python3 -m src.birdbird.cli (this will fail)
# ALWAYS use: birdbird command (after pip install -e .)
# Examples:

birdbird filter /path/to/clips

# Generate highlights reel from filtered clips
birdbird highlights /path/to/clips/has_birds/

# Run filter + highlights + songs in one step (clears existing has_birds with --force)
birdbird process /path/to/clips --force

# Test with limited clips
birdbird filter /path/to/clips --limit 10

# Publish highlights to Cloudflare R2
birdbird publish /path/to/clips

# Detect bird songs using BirdNET (standalone step)
birdbird songs /path/to/clips
birdbird songs /path/to/clips --min-conf 0.3 --limit 10

# Preview viewer changes locally (before deploying)
npx serve -l 3000 src/birdbird/templates
# Then open: http://localhost:3000/viewer.html
# Edit src/birdbird/templates/viewer.html and refresh browser to see changes
# Note: R2 bucket CORS must include http://localhost:3000
```

## Architecture

```
src/birdbird/
├── __init__.py      # Package metadata
├── cli.py           # Typer CLI entry point
├── config.py        # load_config() - reads ~/.birdbird/config.json
├── detector.py      # BirdDetector class (YOLOv8-nano, COCO bird class)
├── filter.py        # filter_clips() - batch processing, saves detections.json
├── highlights.py    # generate_highlights() - segment extraction + concatenation
├── frames.py        # extract_and_score_frames() - standalone frame scoring (not in main pipeline)
├── publish.py       # publish_to_r2() - R2 upload with batch management
├── songs.py         # analyze_songs() - BirdNET audio analysis for bird vocalizations
└── templates/
    ├── viewer.html  # Static web viewer template
    └── credits.html # Credits page listing dependencies and licenses
```

**Important**: When adding new dependencies to `pyproject.toml`, update `templates/credits.html` with the new library, its purpose, and license information.

**Detection approach**: Weighted frame sampling (4x in first second, then 1fps), YOLOv8-nano for COCO class 14 (bird).

**Highlights approach**: Binary search for segment boundaries using cached detection timestamps from filter step. Concatenation via ffmpeg.

**Publish approach**: Uploads highlights.mp4 to Cloudflare R2 with YYYYMMDD-NN batch naming. Maintains latest.json index for web viewer. Prompts before deleting old batches (>5). Static HTML viewer fetches from R2 via client-side JavaScript.

**Viewer development**: Use `npx serve -l 3000 src/birdbird/templates` to test viewer changes locally without deploying. Viewer fetches directly from R2 bucket (requires CORS configuration allowing localhost:3000). After confirming changes, copy to birdbird-website repo and push to deploy.

**Songs approach**: Extracts audio from AVI files to temporary WAV files (ffmpeg), runs BirdNET-Analyzer for bird vocalization detection. Outputs songs.json with all detections including species (common/scientific names), confidence, filename, and timestamps. Configurable confidence threshold (default 0.25). Location filtering available via --lat/--lon for regional species filtering.

**Configuration**: User settings stored in `~/.birdbird/config.json`. Currently supports:
- `location.lat` / `location.lon` - Default coordinates for BirdNET species filtering (can be overridden with --lat/--lon CLI flags)

## Milestone Tracker

- [x] M1: Bird detection filter (498 clips, 29.9% detection rate)
- [x] M2: Highlights reel v1 (binary search for segment boundaries)
- [ ] M3: Species-specific frame extraction (using M4 detections)
- [x] M4: Species detection (BioCLIP visual identification)
- [ ] M5: Email report
- [ ] M6: Highlights reel v2
- [ ] M7: Cloud storage

## Saved Plans

Use `/plan` to list plans or `/plan <name>` to load details. Plans are stored in `~/.claude/plans/`.

| Name | Status | Domain | Summary |
|------|--------|--------|---------|
| `viewer-ui` | Implemented | Frontend | Date range support, simplified UI |
| `captions` | Planned | Backend | M2.1: Detection confidence overlay |
| `publish` | Implemented | Both | M2.2: R2 upload, static web viewer |
| `audio-tab` | Ready | Frontend | Audio statistics tab in viewer |
| `m4-species` | Ready | Backend | BioCLIP visual species identification |

**Key references** (available in full plans):
- Website repo: `/home/ross/src/birdbird-website/` (auto-deploys on push)
- Deployment URL: https://birdbird.rossarn.workers.dev/
- Remote GPU: `ssh devserver@192.168.1.146` (for M4 species detection)
