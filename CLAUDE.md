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

# Test with limited clips
birdbird filter /path/to/clips --limit 10
```

## Architecture

```
src/birdbird/
├── __init__.py      # Package metadata
├── cli.py           # Typer CLI entry point
├── detector.py      # BirdDetector class (YOLOv8-nano, COCO bird class)
├── filter.py        # filter_clips() - batch processing, saves detections.json
└── highlights.py    # generate_highlights() - segment extraction + concatenation
```

**Detection approach**: Weighted frame sampling (4x in first second, then 1fps), YOLOv8-nano for COCO class 14 (bird) and class 0 (person, for close-ups).

**Highlights approach**: Binary search for segment boundaries using cached detection timestamps from filter step. Crossfade transitions via ffmpeg.

## Milestone Tracker

- [x] M1: Bird detection filter (498 clips, 29.9% detection rate)
- [x] M2: Highlights reel v1 (binary search + crossfade transitions)
- [ ] M3: Frame capture
- [ ] M4: Species detection
- [ ] M5: Email report
- [ ] M6: Highlights reel v2
- [ ] M7: Cloud storage
