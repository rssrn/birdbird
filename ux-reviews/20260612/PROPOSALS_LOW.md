# BirdBird UX Improvement Proposals - Low Priority

Source: GitHub issue #33 (yellow-hat autonomous agent review, 2026-06-12)

## Status Legend

- 🔵 Proposed - awaiting decision
- ✅ Accepted - approved for implementation
- ❌ Rejected - declined

---

### LOW-01: Surface BioCLIP runners-up in species view

**Status:** 🔵 Proposed

**Description:**
Every species detection in `species.json` includes a `runners_up` field — the top 3 alternative species BioCLIP considered, with confidence scores. This data is correctly serialised but never displayed in the viewer.

Adding an "Also could be..." section under each identification would make the model's uncertainty visible and increase trust in the results.

**Rationale:**
- Zero backend work — data already arrives in every published batch
- Increases transparency: users can see when identification was confident vs. ambiguous
- Requires only a viewer change (render the existing `runners_up` array)

**Effort estimate:** Low — pure viewer change, data already present

**Source:** Issue #33 suggestion 2

---

### LOW-02: Promote `frames` command to standard pipeline step

**Status:** ❌ Rejected

**Description (from issue #33):**
Suggestion to unhide `birdbird frames` and add it to `birdbird process` as a standard step.

**Why rejected:**
`frames.py` was a deliberate earlier approach — still-image quality scoring as the primary output. It was explicitly removed from the pipeline in commit `80105cd` ("Remove frame scoring from pipeline") after `best_clips.py` was introduced, which achieves the same goal (finding the best sighting moment per species) via video clip seeking rather than JPEG extraction. The two approaches are not complementary at the pipeline level; `best_clips` superseded `frames` as the pipeline's "best moment" mechanism. The `frames` command remains available as a standalone tool but promoting it to a default step would regress a deliberate design decision.

**Source:** Issue #33 suggestion 5
