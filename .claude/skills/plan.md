# Plan Loader Skill

Load detailed implementation plans for the birdbird project on demand.

## Usage

- `/plan` - List all available plans with status and domain
- `/plan <name>` - Load a specific plan by name (supports partial matching)

## Available Plans

| Short Name | File | Status | Domain | Description |
|------------|------|--------|--------|-------------|
| `viewer-ui` | `birdbird-viewer-ui-improvements.md` | Implemented | Frontend | Date range support, simplified UI |
| `captions` | (inline in CLAUDE.md) | Planned | Backend | M2.1: Detection confidence overlay |
| `publish` | `idempotent-bouncing-thimble.md` | Implemented | Both | M2.2: R2 upload + web viewer |
| `audio-tab` | `goofy-finding-volcano.md` | Ready | Frontend | Audio statistics tab in viewer |
| `m4-species` | `birdbird-m4-species-integration.md` | Ready | Backend | BioCLIP visual species identification |

## Instructions

When invoked with `/plan`:

1. **No arguments**: Display the table above showing all plans with their status and domain.

2. **With a plan name**: Read and return the full plan file from `~/.claude/plans/`. Match using:
   - Exact short name match (e.g., `viewer-ui`)
   - Partial match on short name (e.g., `viewer` matches `viewer-ui`)
   - Partial match on filename (e.g., `species` matches `birdbird-m4-species-integration.md`)

3. **Special case - `captions`**: This plan is stored inline. Return:
   ```
   ## M2.1: Highlights Reel Captions

   **Status**: Planned (not yet implemented)
   **Domain**: Backend (highlights.py)

   ### Summary
   Add detection confidence overlay to highlight segments.

   ### Requirements
   - **Placement**: Top-left corner (existing camera timestamp is bottom-left)
   - **Font**: Match style and size of embedded camera timestamp (white text with black shadow)
   - **Format**: "Bird 85%" (confidence percentage)
   - **Always visible**: Display throughout entire segment duration

   ### Implementation
   - Enhance `Segment` dataclass to include `detection_confidence`
   - Update `find_bird_segments()` to track and return detection metadata
   - Modify `extract_segment()` to add ffmpeg drawtext filter with detection info

   ### Reference
   Sample frame: `/home/ross/BIRDS/20260114/1112062500.avi` shows existing timestamp style
   ```

4. **Not found**: If no match, list available plans and suggest the closest match.

## Domain Guide

- **Frontend**: Changes to `templates/index.html` or `templates/credits.html`. Test with `npx serve`.
- **Backend**: Changes to Python modules in `src/birdbird/`. Test with `birdbird` CLI commands.
- **Both**: Changes spanning templates and Python code.
