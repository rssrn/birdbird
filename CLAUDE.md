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
# Install in development mode
pip install -e .

# Run the filter command
birdbird filter /path/to/clips --confidence 0.3 --sample-fps 1.0

# Test with limited clips
birdbird filter /path/to/clips --limit 10
```

## Architecture

```
src/birdbird/
├── __init__.py      # Package metadata
├── cli.py           # Typer CLI entry point
├── detector.py      # BirdDetector class (YOLOv8-nano, COCO bird class)
└── filter.py        # filter_clips() - batch processing logic
```

**Detection approach**: Sample frames at configurable FPS (default 1fps), run YOLOv8-nano, check for COCO class 14 (bird) above confidence threshold.

## M1 Implementation Plan

### Status: Tested on 50 clips (34% detection rate), full batch pending

**Completed:**
- [x] Project structure (pyproject.toml, hatchling build)
- [x] BirdDetector class with YOLOv8-nano
- [x] Dual-class detection: bird (0.2 conf) + person (0.3 conf) for close-ups
- [x] Weighted frame sampling: 5 frames in first 1s, then 1fps
- [x] CLI with configurable confidence thresholds
- [x] Batch filter with progress bar and detection rate stats
- [x] Tested on 50 clips: 34% detection rate, spot-checked true positives

**Next session TODOs:**
- [ ] Run on full batch (498 clips) - expect ~19 minutes
- [ ] Review results and spot-check a few more clips
- [ ] Consider adding .venv to .gitignore
- [ ] Update milestone tracker when M1 is confirmed complete

## Milestone Tracker

- [ ] M1: Bird detection filter (in progress)
- [ ] M2: Highlights reel v1
- [ ] M3: Frame capture
- [ ] M4: Species detection
- [ ] M5: Email report
- [ ] M6: Highlights reel v2
- [ ] M7: Cloud storage
