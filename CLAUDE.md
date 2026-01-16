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

# Publish highlights to Cloudflare R2
birdbird publish /path/to/clips
```

## Architecture

```
src/birdbird/
├── __init__.py      # Package metadata
├── cli.py           # Typer CLI entry point
├── detector.py      # BirdDetector class (YOLOv8-nano, COCO bird class)
├── filter.py        # filter_clips() - batch processing, saves detections.json
├── highlights.py    # generate_highlights() - segment extraction + concatenation
├── frames.py        # extract_and_score_frames() - quality-based frame ranking
├── publish.py       # publish_to_r2() - R2 upload with batch management
└── templates/
    └── viewer.html  # Static web viewer template
```

**Detection approach**: Weighted frame sampling (4x in first second, then 1fps), YOLOv8-nano for COCO class 14 (bird) and class 0 (person, for close-ups).

**Highlights approach**: Binary search for segment boundaries using cached detection timestamps from filter step. Crossfade transitions via ffmpeg.

**Frames approach**: Multi-factor scoring (confidence, sharpness, bird size, position) with weighted combination. Extracts top-N frames ranked by quality. Timing instrumentation tracks ms/frame for each factor.

**Publish approach**: Uploads highlights.mp4 + top 3 frames to Cloudflare R2 with YYYYMMDD-NN batch naming. Maintains latest.json index for web viewer. Prompts before deleting old batches (>5). Static HTML viewer fetches from R2 via client-side JavaScript.

## Milestone Tracker

- [x] M1: Bird detection filter (498 clips, 29.9% detection rate)
- [x] M2: Highlights reel v1 (binary search + crossfade transitions)
- [x] M3: Frame capture (multi-factor quality scoring)
- [ ] M4: Species detection
- [ ] M5: Email report
- [ ] M6: Highlights reel v2
- [ ] M7: Cloud storage

## Saved Plans

**M2.1: Highlights Reel Captions**
- Status: Planned (not yet implemented)
- Summary: Add detection metadata overlay to highlight segments showing match type and confidence
- Requirements:
  - **Placement**: Top-left corner (existing camera timestamp is bottom-left)
  - **Font**: Match style and size of embedded camera timestamp (white text with black shadow)
  - **Format**: "Bird 85%" (detection type + confidence percentage)
  - **Multiple detections**: Show both if present, highest confidence first
    - Example: "Bird 85% • Person 45%"
  - **Always visible**: Display throughout entire segment duration
- Implementation considerations:
  - Enhance `Segment` dataclass to include `detection_type` and `detection_confidence`
  - Update `find_bird_segments()` to track and return detection metadata
  - Modify `extract_segment()` to add ffmpeg drawtext filter with detection info
  - May need to track multiple detections per segment (bird + person)
- Sample frame reference: `/home/ross/BIRDS/20220114/1112062500.avi` shows existing timestamp style

**M2.2: Publish Highlights to Cloudflare R2 + Workers**
- Plan file: `/home/ross/.claude/plans/idempotent-bouncing-thimble.md`
- Status: Implemented
- Summary: Upload highlights.mp4 + top 3 frames to R2 with static web viewer
- Implementation: `publish.py` module, `birdbird publish` command, `templates/viewer.html`
- Website repo: `/home/ross/src/birdbird-website/` (auto-deploys to Cloudflare on push to main)
- Deployment URL: https://birdbird.rossarn.workers.dev/
- Next steps: Copy viewer.html to birdbird-website, configure R2 base URL, push to deploy

## TODOs

**Evaluate Person Detection Feature**
- **Context**: Person detection (COCO class 0) was added to catch close-up birds misclassified as "person". However, it may be causing more false positives (garden decorations) than catching legitimate birds.
- **Task**: Review clips that were included via person detection to determine hit rate:
  1. Extract all clips from a batch where `detection_type == "person"` in `detections.json`
  2. Manually review each clip to count: (a) actual birds, (b) false positives
  3. Calculate hit rate: actual_birds / total_person_detections
  4. Decision: If hit rate is low (<30%), consider removing person detection entirely
- **Example batch**: `/home/ross/BIRDS/20220116/` has 136 person detections (confidence 0.30-0.63)
- **Known false positive**: Clips 1509211200-1509251100 (5 clips, ~23s in highlights) detected decorations as "person" at 0.326-0.394 confidence
- **Command to extract person-detected clips**:
  ```bash
  cat detections.json | jq -r 'to_entries[] | select(.value.detection_type == "person") | .key'
  ```
