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

```bash
# Setup: Create and activate virtual environment (recommended)
python3 -m venv .venv
source .venv/bin/activate  # On Linux/Mac
# .venv\Scripts\activate   # On Windows

# Install in development mode
pip install -e .

# Run commands (if using venv without activating, prefix with .venv/bin/)
birdbird filter /path/to/clips
# Or: .venv/bin/birdbird filter /path/to/clips

# Generate highlights reel from filtered clips
birdbird highlights /path/to/clips/has_birds/

# Run filter + highlights in one step (clears existing has_birds with --force)
birdbird process /path/to/clips --force

# Extract top 20 frames from filtered clips
birdbird frames /path/to/clips/has_birds/

# Extract top 50 frames
birdbird frames /path/to/clips/has_birds/ --top-n 50

# Test with limited clips
birdbird filter /path/to/clips --limit 10
birdbird frames /path/to/clips/has_birds/ --limit 5 --top-n 10

# Publish highlights to Cloudflare R2
birdbird publish /path/to/clips

# Detect bird songs using BirdNET (standalone step)
birdbird songs /path/to/clips
birdbird songs /path/to/clips --min-conf 0.3 --limit 10

# Preview viewer changes locally (before deploying)
python preview_viewer.py
# Then open: http://localhost:8000/viewer.html
# Edit src/birdbird/templates/viewer.html and refresh browser to see changes
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
├── frames.py        # extract_and_score_frames() - quality-based frame ranking
├── publish.py       # publish_to_r2() - R2 upload with batch management
├── songs.py         # analyze_songs() - BirdNET audio analysis for bird vocalizations
└── templates/
    ├── viewer.html  # Static web viewer template
    └── credits.html # Credits page listing dependencies and licenses
```

**Important**: When adding new dependencies to `pyproject.toml`, update `templates/credits.html` with the new library, its purpose, and license information.

**Detection approach**: Weighted frame sampling (4x in first second, then 1fps), YOLOv8-nano for COCO class 14 (bird).

**Highlights approach**: Binary search for segment boundaries using cached detection timestamps from filter step. Crossfade transitions via ffmpeg.

**Frames approach**: Multi-factor scoring (confidence, sharpness, bird size, position) with weighted combination. Extracts top-N frames ranked by quality. Timing instrumentation tracks ms/frame for each factor.

**Publish approach**: Uploads highlights.mp4 + top 3 frames to Cloudflare R2 with YYYYMMDD-NN batch naming. Maintains latest.json index for web viewer. Prompts before deleting old batches (>5). Static HTML viewer fetches from R2 via client-side JavaScript.

**Viewer development**: Use `preview_viewer.py` to test viewer changes locally without deploying. Server runs on localhost:8000 and proxies R2 requests to avoid CORS. Viewer auto-detects localhost and uses proxy. After confirming changes, copy to birdbird-website repo and push to deploy.

**Songs approach**: Extracts audio from AVI files to temporary WAV files (ffmpeg), runs BirdNET-Analyzer for bird vocalization detection. Outputs songs.json with all detections including species (common/scientific names), confidence, filename, and timestamps. Configurable confidence threshold (default 0.25). Location filtering available via --lat/--lon for regional species filtering.

**Configuration**: User settings stored in `~/.birdbird/config.json`. Currently supports:
- `location.lat` / `location.lon` - Default coordinates for BirdNET species filtering (can be overridden with --lat/--lon CLI flags)

## Milestone Tracker

- [x] M1: Bird detection filter (498 clips, 29.9% detection rate)
- [x] M2: Highlights reel v1 (binary search + crossfade transitions)
- [x] M3: Frame capture (multi-factor quality scoring)
- [ ] M4: Species detection
- [ ] M5: Email report
- [ ] M6: Highlights reel v2
- [ ] M7: Cloud storage

## Saved Plans

**Viewer UI Improvements & Date Ranges**
- Plan file: `/home/ross/.claude/plans/birdbird-viewer-ui-improvements.md`
- Status: Implemented
- Summary: Made viewer less technical, added multi-day date range support with timestamp validation
- Implemented changes:
  - Fixed filename format docs (actual: `DDHHmmss00.avi`, not `MMDDHHmmss.avi`)
  - Added `extract_date_range()` in publish.py with timestamp validation (scans parent directory)
  - Validates directory date falls within filename date range; falls back if camera clock incorrect
  - Metadata includes `start_date` and `end_date` fields
  - Simplified UI: removed frame captions, batch IDs; shows human-readable dates ("11-14 Jan")
  - Added location (Holt, Wiltshire) to subtitle
  - Archive buttons at top with accessible current selection indicator (black border)
  - Created `update_metadata.py` script to update existing R2 batches without re-upload

**M2.1: Highlights Reel Captions**
- Status: Planned (not yet implemented)
- Summary: Add detection confidence overlay to highlight segments
- Requirements:
  - **Placement**: Top-left corner (existing camera timestamp is bottom-left)
  - **Font**: Match style and size of embedded camera timestamp (white text with black shadow)
  - **Format**: "Bird 85%" (confidence percentage)
  - **Always visible**: Display throughout entire segment duration
- Implementation considerations:
  - Enhance `Segment` dataclass to include `detection_confidence`
  - Update `find_bird_segments()` to track and return detection metadata
  - Modify `extract_segment()` to add ffmpeg drawtext filter with detection info
- Sample frame reference: `/home/ross/BIRDS/20260114/1112062500.avi` shows existing timestamp style

**M2.2: Publish Highlights to Cloudflare R2 + Workers**
- Plan file: `/home/ross/.claude/plans/idempotent-bouncing-thimble.md`
- Status: Implemented
- Summary: Upload highlights.mp4 + top 3 frames to R2 with static web viewer
- Implementation: `publish.py` module, `birdbird publish` command, `templates/viewer.html`
- Website repo: `/home/ross/src/birdbird-website/` (auto-deploys to Cloudflare on push to main)
- Deployment URL: https://birdbird.rossarn.workers.dev/
- Next steps: Copy viewer.html to birdbird-website, configure R2 base URL, push to deploy

**Audio Statistics Tab in Viewer**
- Plan file: `/home/ross/.claude/plans/goofy-finding-volcano.md`
- Status: Planned (ready for implementation)
- Summary: Add 2-tab interface to viewer showing Highlights (existing) and Audio (new) tabs
- Requirements:
  - Tab 1 (Highlights): Existing video + frames content (no changes to content itself)
  - Tab 2 (Audio): Horizontal bar chart showing bird vocalization statistics from songs.json
  - Bar chart shows: common name, count (sorted descending), proportional bar, confidence display
  - Confidence format: single "54%", 2-3 "54%, 78%", 4+ "54-78%" (range)
  - Explanatory text about ambient audio sampling from motion-triggered clips
- Implementation: Single file change (`templates/viewer.html`) - adds tabs, CSS, JavaScript
- Testing: Use `python3 preview_viewer.py` for local demo before deployment
- Next steps: Implement per plan, test locally, copy to birdbird-website, deploy

**M4: Visual Species Identification Research**
- Plan file: `/home/ross/.claude/plans/birdbird-visual-species-identification.md`
- Status: Research complete, implementation blocked by hardware
- Summary: Researched options for identifying bird species from video frames
- Options evaluated:
  - **HuggingFace classifiers**: Poor UK species coverage (only 3/22 species matched)
  - **iNaturalist API**: Excellent coverage but not publicly accessible (fee-based)
  - **BioCLIP** (`pybioclip`): Best option - 454K+ taxa, MIT license, but very slow on CPU
  - **NIA/Obsidentify**: European-focused, worth investigating API access
- Problem: BioCLIP too slow without GPU (model load + inference takes many minutes on CPU)
- Next steps: Try BioCLIP on GPU (Colab), or investigate NIA API, or hybrid approach with smaller label set
- Test frames: `/tmp/bioclip_test/frame_0[1-5].jpg` (from Jan 21 highlights)
- UK birds list: 67 species curated from BTO, saved in plan file

