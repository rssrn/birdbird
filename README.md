# birdbird

Automated bird feeder video analysis pipeline. Processes motion-triggered clips from a bird feeder camera to identify bird species, generate highlight reels, and produce summary reports.

## Quickstart

```bash
# Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install in development mode
pip install -e .

# Process clips: filter + generate highlights in one step
birdbird process /path/to/clips

# Test with limited clips first
birdbird process /path/to/clips --limit 10

# Or run steps separately:
birdbird filter /path/to/clips
birdbird highlights /path/to/clips/has_birds/
```

## Technical Overview

### Architecture

```
src/birdbird/
├── cli.py           # Typer CLI entry point
├── detector.py      # BirdDetector class (YOLOv8-nano)
├── filter.py        # Batch filtering logic
└── highlights.py    # Highlights reel generation
```

### Detection Approach

Uses **YOLOv8-nano** pre-trained on [COCO](https://cocodataset.org/) (Common Objects in Context), a dataset with 80 object categories including birds. This allows detection without custom training:

- **Bird detection**: COCO class 14 (bird) with confidence threshold 0.2
- **Close-up detection**: COCO class 0 (person) with confidence threshold 0.3 — large birds filling the frame are sometimes misclassified as "person" by YOLO, so we accept these as bird detections

### Frame Sampling Strategy

To balance speed and accuracy, frames are sampled with weighted density:

- **First second**: ~4 samples (every 0.25s) — captures the motion trigger event
- **Remaining duration**: 1 sample per second — catches birds that land after initial motion

This allows processing ~10s clips in ~2.3 seconds while catching brief bird appearances.

### Output

- **Filter**: Clips containing detected birds are copied to a `has_birds/` subdirectory
- **Highlights**: MP4 reel concatenating bird activity segments with crossfade transitions

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

| # | Milestone | Description | Status |
|---|-----------|-------------|--------|
| M1 | Bird detection filter | Discard clips without birds (eliminate wind false positives) | Done |
| M2 | Highlights reel v1 | Concatenate segments with bird activity with crossfade transitions | Done |
| M3 | Frame capture | Extract in-focus bird frames with timestamps | |
| M4 | Species detection | Identify species, generate timeline summary with frame captures | |
| M5 | Email or static web report | Automated summary reports via email | |
| M6 | Highlights reel v2 | Curated "best action" clips | |
| M7 | Cloud storage | S3 storage for frames/clips, database backend | |

## Other Feature Ideas
| # | Feature | Description |
|---|-----------|-------------|
| F1 | Other objects | If other misc objects are detected with a
separate confidence threshold, note those.  Might get some squirrels,
cats, etc. |



## Input Format

- **Source**: Bird feeder camera with motion detection
- **Format**: AVI (MJPEG, 1440x1080, 30fps, ~10 seconds, ~27MB each)
- **Filename**: `MMDDHHmmss.avi` (timestamp when clip was captured)
- **Batches**: Downloaded every few days into dated directories (e.g., `20220114/`)
