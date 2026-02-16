# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

birdbird - Bird feeder video analysis pipeline. See README.md for full project description and milestones.

## Directory Structure

**Important for file operations**: This project uses Python src-layout:
- Project root: `/home/ross/src/birdbird/`
- Python package: `/home/ross/src/birdbird/src/birdbird/`
- Template files: `/home/ross/src/birdbird/src/birdbird/templates/`

When editing files, always use the full absolute path shown in Read tool results, not relative paths inferred from the architecture diagram.

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
birdbird highlights /path/to/clips

# Run filter + highlights + songs in one step (clears existing working directory with --force)
# Add --species to also run visual species identification + best_clips
birdbird process /path/to/clips --force

# Test with limited clips
birdbird filter /path/to/clips --limit 10

# Publish highlights to Cloudflare R2
birdbird publish /path/to/clips

# Detect bird songs using BirdNET (standalone step)
birdbird songs /path/to/clips
birdbird songs /path/to/clips --min-conf 0.3 --limit 10

# Run visual species identification (standalone step, requires remote GPU by default)
birdbird species /path/to/clips

# Find best sighting moments per species (standalone; also runs automatically after species in process)
birdbird best_clips /path/to/clips

# Preview viewer changes locally (before deploying)
npx serve -l 3000 src/birdbird/templates
# Then open: http://localhost:3000/index.html
# Edit src/birdbird/templates/index.html and refresh browser to see changes
# Note: R2 bucket CORS must include http://localhost:3000
```

## Testing

**IMPORTANT**: This project maintains high test coverage (167 tests). When adding or modifying functionality, ALWAYS create corresponding mock tests following the existing patterns in `tests/`. Mock external dependencies (YOLO, BioCLIP, BirdNET, ffmpeg, S3, etc.) using `unittest.mock.patch` and `sys.modules` injection as shown in existing test files.

**Test organization**: Tests use pytest markers to distinguish between fast and slow tests:
- Fast tests (all current tests): No marker needed - these run in pre-commit hooks
- Slow tests (integration, real dependencies): Mark with `@pytest.mark.slow` - excluded from pre-commit

**Running tests:**
```bash
# Fast tests only (runs in pre-commit)
pytest -m "not slow"

# All tests
pytest

# Only slow tests
pytest -m slow
```

**When implementing new functionality:**
1. **Write code** in `src/birdbird/`
2. **Write mock tests** in `tests/test_<module>_mock.py` - see `test_species_mock.py` for patterns
3. **Run tests** with `pytest -m "not slow"` to verify
4. Follow existing patterns: mock external dependencies, test edge cases, verify logic

**Test layers:**
- Layer 1 (pure unit tests): No marker needed - tests that don't require any external dependencies
- Layer 2 (mocked unit tests): No marker unless unusually slow - mock external dependencies (torch, bioclip, ffmpeg, etc.)
- Layer 3 (integration tests with real dependencies): Always use `@pytest.mark.slow` - tests that require actual GPU, video files, etc.

## Architecture

```
src/birdbird/
├── __init__.py      # Package metadata
├── cli.py           # Typer CLI entry point
├── config.py        # load_config() - reads ~/.birdbird/config.json
├── paths.py         # Path utilities for output directories and file locations
├── detector.py      # BirdDetector class (YOLOv8-nano, COCO bird class)
├── species.py       # SpeciesDetector class (BioCLIP visual species identification)
├── filter.py        # filter_clips() - batch processing, saves detections.json
├── highlights.py    # generate_highlights() - segment extraction + concatenation
├── best_clips.py    # find_best_clips() - identifies best sighting moments per species
├── frames.py        # extract_and_score_frames() - standalone frame scoring (not in main pipeline)
├── publish.py       # publish_to_r2() - R2 upload with batch management
├── songs.py         # analyze_songs() - BirdNET audio analysis for bird vocalizations
└── templates/       # Static web viewer files
    ├── index.html   # Main viewer page with tabs for highlights/video/audio stats
    ├── method.html  # How it works page
    ├── credits.html # Credits page listing dependencies and licenses
    ├── accessibility.html # Accessibility statement
    ├── styles.css   # Shared styles for all pages
    ├── config.js    # R2 bucket URL configuration (deployed version)
    ├── config.local.js # Local R2 URL override (gitignored, for development)
    ├── config-loader.js # Config loading logic
    └── favicon.*    # Site icons
```

**Important**: When adding new dependencies to `pyproject.toml`, update `templates/credits.html` with the new library, its purpose, and license information.

**Output structure**: The pipeline creates two directories under `birdbird/`:
- `birdbird/working/` - Temporary/intermediate files (symlinks to filtered clips, frame candidates, etc.)
- `birdbird/assets/` - Final outputs that mirror R2 structure (highlights.mp4, detections.json, songs.json, species.json, etc.)

**Detection approach**: Weighted frame sampling (4x in first second, then 1fps), YOLOv8-nano for COCO class 14 (bird).

**Highlights approach**: Binary search for segment boundaries using cached detection timestamps from filter step. Concatenation via ffmpeg.

**Publish approach**: Uploads highlights.mp4 to Cloudflare R2 with YYYYMMDD-NN batch naming. Maintains latest.json index for web viewer. Prompts before deleting old batches (>5). Static HTML viewer fetches from R2 via client-side JavaScript.

**Viewer development**: Use `npx serve -l 3000 src/birdbird/templates` to test viewer changes locally without deploying. Viewer fetches directly from R2 bucket (requires CORS configuration allowing localhost:3000). After confirming changes, copy to birdbird-website repo and push to deploy.

**Chrome headless screenshots**: When evaluating viewer designs or capturing UI state, use Chrome headless mode:
```bash
# Basic screenshot
google-chrome --headless --screenshot=/tmp/output.png --window-size=1400,900 http://localhost:3000/index.html 2>/dev/null

# For pages that need load time (JavaScript content)
google-chrome --headless --screenshot=/tmp/output.png --window-size=1400,2400 --virtual-time-budget=5000 http://localhost:3000/index.html 2>/dev/null

# For specific tabs or query parameters
google-chrome --headless --screenshot=/tmp/output.png --window-size=1400,2400 --virtual-time-budget=5000 'http://localhost:3000/index.html?tab=audio' 2>/dev/null
```
- Use `--virtual-time-budget=5000` (5 seconds) to allow async content to load
- Larger `--window-size` (e.g., 1400x2400) captures more of the page
- Always use single quotes around URLs with query parameters to avoid shell issues
- The `2>/dev/null` suppresses Chrome's stderr output

**Songs approach**: Extracts audio from AVI files to temporary WAV files (ffmpeg), runs BirdNET-Analyzer for bird vocalization detection. Outputs songs.json with all detections including species (common/scientific names), confidence, filename, and timestamps. Configurable confidence threshold (default 0.25). Location filtering available via --lat/--lon for regional species filtering.

**Configuration**: User settings stored in `~/.birdbird/config.json`. Currently supports:
- `location.lat` / `location.lon` - Default coordinates for BirdNET species filtering (can be overridden with --lat/--lon CLI flags)
- `species.labels_file` - Path to custom species labels file for BioCLIP (optional; defaults to built-in `src/birdbird/data/uk_garden_birds.txt` with 67 UK species)
- `species.processing.mode` - Processing mode: "remote" (recommended), "local" (disabled to prevent slowdown), or "cloud" (not implemented)
- `species.processing.remote.*` - Remote GPU configuration (host, shell, python_env, timeout)


## Saved Plans

Use `/plan` to list plans or `/plan <name>` to load details. Plans are stored in `~/.claude/plans/`.

| Name | Status | Domain | Summary |
|------|--------|--------|---------|
| `captions` | Planned | Backend | Detection confidence overlay |

**Key references** (available in full plans):
- Website repo: `/home/ross/src/birdbird-website/` (auto-deploys on push)
- Deployment URL: https://birdbird.rossarn.workers.dev/
- Remote GPU: `ssh user@gpu-server.local` (for M4 species detection)
