# birdbird

Automated bird feeder video analysis pipeline. Processes motion-triggered clips from a bird feeder camera to identify bird species, generate highlight reels, and produce summary reports.

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

| # | Milestone | Description |
|---|-----------|-------------|
| M1 | Bird detection filter | Discard clips without birds (eliminate wind false positives) |
| M2 | Highlights reel v1 | Concatenate segments with bird activity using improved motion detection |
| M3 | Frame capture | Extract in-focus bird frames with timestamps |
| M4 | Species detection | Identify species, generate timeline summary with frame captures |
| M5 | Email report | Automated summary reports via email |
| M6 | Highlights reel v2 | Curated "best action" clips |
| M7 | Cloud storage | S3 storage for frames/clips, database backend |

## Input Format

- **Source**: Bird feeder camera with motion detection
- **Format**: AVI (MJPEG, 1440x1080, 30fps, ~10 seconds, ~27MB each)
- **Filename**: `MMDDHHmmss.avi` (timestamp when clip was captured)
- **Batches**: Downloaded every few days into dated directories (e.g., `20220114/`)