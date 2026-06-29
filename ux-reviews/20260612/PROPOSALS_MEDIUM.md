# BirdBird UX Improvement Proposals - Medium Priority

Source: GitHub issue #33 (yellow-hat autonomous agent review, 2026-06-12)

## Status Legend

- 🔵 Proposed - awaiting decision
- ✅ Accepted - approved for implementation
- ❌ Rejected - declined

---

### MED-01: Connect frame-scoring pipeline to the viewer

**Status:** 🔵 Proposed

**Description:**
`frames.py` scores extracted frames using Laplacian sharpness, bird bbox size, edge-clipping penalty, and detection confidence — producing a ranked list of the best sighting frames across a batch. The output (`frame_scores.json`, top JPEG frames) is written to assets but never published to R2 or shown in the viewer.

Wiring this in would surface the best still image from each batch as a thumbnail/poster in the viewer.

**Rationale:**
- Scoring logic, normalization, and top-frame extraction are fully built and tested
- No algorithmic work needed — purely plumbing: publish step + viewer display
- A "best photo of the day" surface would be distinctive and visually compelling

**Effort estimate:** Medium — requires changes to `publish.py` (upload frame JPEGs to R2) and viewer (display thumbnail/poster per batch)

**Source:** Issue #33 suggestion 1

---

### MED-02: Expose timestamp reliability badge in the viewer

**Status:** 🔵 Proposed

**Description:**
The pipeline validates camera timestamps against the directory name and writes a `timestamps_reliable: bool` flag into `songs.json` metadata. The viewer never reads or displays this flag.

A simple badge in the audio/songs tab — e.g. "Timestamps approximate — camera clock was reset" — would prevent user confusion when displayed times don't match expectations.

**Rationale:**
- Detection and flagging pipeline is already fully built
- Pure viewer change (read one existing JSON field, show/hide a badge)
- Prevents silent misinformation in the UI

**Effort estimate:** Low — one conditional display element in the audio tab

**Source:** Issue #33 suggestion 3

---

### MED-03: Species activity timeline chart

**Status:** 🔵 Proposed

**Description:**
Every detection in `species.json` has a precise timestamp. These can power an hourly activity distribution chart in the viewer — e.g. "Blue Tit was most active 8–9am" — with no additional backend work. The same JSON already published to R2 contains everything needed.

**Rationale:**
- Data already exists; no pipeline changes required
- Adds genuine birding value (activity patterns are interesting to birders)
- Natural complement to the existing species identification view

**Considerations:**
- Timestamp reliability must be checked first (see MED-02) — misleading if clock was reset
- Needs decision on per-batch vs. cross-batch aggregation
- Requires frontend chart work (D3, Canvas, or similar)

**Effort estimate:** Medium-High — frontend-only but non-trivial chart implementation

**Source:** Issue #33 suggestion 4
