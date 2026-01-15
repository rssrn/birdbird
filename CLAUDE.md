# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

birdbird - Bird feeder video analysis pipeline. See README.md for full project description and milestones.

## Input Data

- Sample batch: `/home/ross/BIRDS/20220114/` (498 clips)
- Format: AVI (MJPEG 1440x1080 30fps), ~10s duration, ~27MB each
- Filename convention: `MMDDHHmmss.avi` encodes capture timestamp

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
```

## Architecture

```
src/birdbird/
├── __init__.py      # Package metadata
├── cli.py           # Typer CLI entry point
├── detector.py      # BirdDetector class (YOLOv8-nano, COCO bird class)
├── filter.py        # filter_clips() - batch processing, saves detections.json
├── highlights.py    # generate_highlights() - segment extraction + concatenation
└── frames.py        # extract_and_score_frames() - quality-based frame ranking
```

**Detection approach**: Weighted frame sampling (4x in first second, then 1fps), YOLOv8-nano for COCO class 14 (bird) and class 0 (person, for close-ups).

**Highlights approach**: Binary search for segment boundaries using cached detection timestamps from filter step. Crossfade transitions via ffmpeg.

**Frames approach**: Multi-factor scoring (confidence, sharpness, bird size, position) with weighted combination. Extracts top-N frames ranked by quality. Timing instrumentation tracks ms/frame for each factor.

## Milestone Tracker

- [x] M1: Bird detection filter (498 clips, 29.9% detection rate)
- [x] M2: Highlights reel v1 (binary search + crossfade transitions)
- [x] M3: Frame capture (multi-factor quality scoring)
- [ ] M4: Species detection
- [ ] M5: Email report
- [ ] M6: Highlights reel v2
- [ ] M7: Cloud storage
