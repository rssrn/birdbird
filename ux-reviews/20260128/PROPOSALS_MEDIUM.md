# BirdBird UX Improvement Proposals - Medium Priority

## Status Legend
- 🔵 Proposed - awaiting decision
- 🔵 Proposed / QuickWin - can be implemented with HTML/CSS/JS only (no backend changes)
- ✅ Accepted - approved for implementation
- ❌ Rejected - declined

---

## Global / Cross-View

### MED-01: Add Tab Explainer Subtitles

**Status:** 🔵 Proposed / QuickWin

**Description:**
Add one-line explanatory subtitles below each tab name to clarify what each view shows:
- Highlights: "Best examples per species"
- Video Stats: "On-camera visual detections"
- Audio Stats: "Off-camera sound detections"

**Rationale:**
- The relationship between three views isn't immediately obvious (Claude Opus 4.5)
- First-time visitors wonder why different species lists appear in different tabs
- The existing explanatory text ("Birds were likely off-camera") helps but could be more prominent
- Helps users understand the detection methodology difference

**Suggested by:** ChatGPT (#2 Tabs), Claude Opus 4.5 (#6-7), Gemini 3 (implicit in cross-pollination suggestion)

**Implementation approach:**
- Add `<small>` or subtitle styling under each tab label
- Keep text concise (5-7 words maximum)
- Style in muted color to avoid competing with tab names
- Consider adding small icons (🎥 for Video, 🔊 for Audio, ⭐ for Highlights)

**Response:**

---

### MED-02: Improve Date Range Selector

**Status:** 🔵 Proposed

**Description:**
Enhance date navigation by adding metadata under each date button (e.g., "142 clips", "23 detections") and consider adding a calendar picker or dropdown for larger date ranges.

**Rationale:**
- Current horizontal list will eventually overflow as more data is collected (Gemini 3)
- No indication of data volume differences between date ranges (ChatGPT)
- No obvious way to jump to specific date or view longer time ranges (Claude Opus 4.5)
- Users tracking patterns over time need better temporal navigation

**Suggested by:** ChatGPT (#2.1 Date Range Selector), Claude Opus 4.5 (#18), Gemini 3 (#9 Date Selection)

**Implementation approach:**
- Phase 1: Add light metadata under each date button ("234 clips · 14 species")
- Phase 2: Add dropdown/calendar picker for dates beyond visible range
- Phase 3: Consider "Compare" toggle to show two date ranges side-by-side (Gemini power-user feature)
- Store clip/detection counts in latest.json for quick access
- Visually separate date navigation from content tabs (they currently compete)

**Response:**

---

### MED-03: Explain Relationship Between Views

**Status:** 🔵 Proposed / QuickWin

**Description:**
Add introductory element or FAQ explaining why Video Stats and Audio Stats show different species lists, and what the detection methods reveal about bird behavior.

**Rationale:**
- Users may wonder why Blue Tit dominates video (115) but Common Wood-Pigeon dominates audio (19) (Claude Opus 4.5)
- This reveals genuinely different patterns (visual vs audio detection, different species vocalize more)
- Adds educational value about bird behavior and detection methodology
- Helps users interpret apparent discrepancies between views

**Suggested by:** Claude Opus 4.5 (#23 Data Presentation)

**Implementation approach:**
- Add collapsible "About this data" or ℹ️ info button near tabs
- Explain: "Video Stats shows birds that appeared on-camera. Audio Stats captures vocalizations from birds that may have been off-camera or hidden in foliage."
- Optional: "Some species are more vocal (Wood-Pigeon), others more visual (Blue Tit at feeder)"
- Could be part of a first-time user onboarding tooltip sequence

**Response:**

---

### MED-04: Clarify "Detection" Definition

**Status:** 🔵 Proposed / QuickWin

**Description:**
Explain what a "detection" represents in video terms - one frame, one continuous appearance, or one event. Add this explanation near the stats displays.

**Rationale:**
- Users don't know what "115 detections" actually means (Claude Opus 4.5)
- Missing context makes numbers hard to interpret meaningfully
- Could be 115 frames from the same bird, or 115 separate visits
- Understanding this affects how users perceive the data

**Suggested by:** Claude Opus 4.5 (#25 Missing Context)

**Implementation approach:**
- Add tooltip or footnote in Video Stats: "Each detection represents one video segment where the species was identified"
- Explain in Audio Stats: "Each vocalization represents one distinct audio event"
- Consider adding this to the proposed "About this data" section (MED-03)
- Update the contextual framing (HIGH-02) to make this clearer

**Response:**

---

## Video Stats View

### MED-05: Add Species List Sorting Options

**Status:** 🔵 Proposed / QuickWin

**Description:**
Allow users to sort the species list by count (default), by confidence level, or alphabetically. Add subtle sorting controls above the list.

**Rationale:**
- Long tail of single detections visually competes with common species (ChatGPT)
- Power users may want to see highest-confidence detections first
- Birders may prefer alphabetical for quick lookup
- Sorting by confidence could help identify most reliable detections

**Suggested by:** ChatGPT (#4.2 Species List Length)

**Implementation approach:**
- Add dropdown or button group above species list: "Sort by: Count | Confidence | A-Z"
- Default to Count (descending) to show most common species first
- Store preference in localStorage
- Update both Video Stats and Audio Stats views
- Consider adding this after implementing HIGH-04 (grouping rare species)

**Response:**

---

## Highlights View

### MED-06: Improve Species Navigation Affordance

**Status:** 🔵 Proposed / QuickWin (Options B, C, D only)

**Description:**
Make the clickable species list more obviously interactive. Add thumbnails, enhanced hover states, or show key metadata (confidence %, duration, time of day) to make the navigation richer.

**Rationale:**
- "Click to jump to best sighting" instruction is easy to miss (Claude Opus 4.5)
- Chevrons help but affordance is still subtle
- Adding thumbnails helps users identify birds faster than reading text (Gemini 3)
- Showing metadata in the list helps users decide which clip to watch

**Suggested by:** ChatGPT (#5.1), Claude Opus 4.5 (#19), Gemini 3 (#20 Visual Affordance)

**Implementation approach:**
- Option A: Add small thumbnail images (cropped from video frame) next to species names
- Option B: Show confidence % and clip duration inline
- Option C: Add stronger hover effects (background color, cursor change)
- Option D: Make the entire species list look more like a menu/playlist
- Consider collapsible tiers (Very Probable / Probable / Possible sections)
- Add filtering option: "Show only Very Probable" (ChatGPT suggestion)

**Response:**

---

### MED-07: Standardize Confidence Tier System

**Status:** 🔵 Proposed / QuickWin

**Description:**
Apply the confidence tier system (Very Probable / Probable / Possible) consistently across all views, not just Highlights. Update Video Stats and Audio Stats to use the same language.

**Rationale:**
- Current inconsistency between Highlights (tiers) and Stats (percentages) may confuse users (Claude Opus 4.5)
- Users trying to understand confidence levels across the app face different systems
- Qualitative labels are more user-friendly than raw percentages
- Creates unified design language

**Suggested by:** Claude Opus 4.5 (#9 Confidence Tiers)

**Implementation approach:**
- Define tier thresholds: Very Probable (>80%), Probable (60-80%), Possible (<60%)
- Replace or supplement percentage ranges in stats views with tier labels
- Use consistent color coding: green for Very Probable, yellow for Probable, orange for Possible
- This could be implemented as part of HIGH-05 (Simplify Confidence Display)
- Add visual badges or icons for each tier

**Response:**

---

## Audio Stats View

### MED-08: Add Waveform Visualizations

**Status:** 🔵 Proposed

**Description:**
Display small waveform visualizations next to each species in the Audio Stats view, allowing users to preview the audio pattern before clicking play.

**Rationale:**
- Makes audio content more discoverable and scannable
- Helps users identify call patterns (short chirps vs long trills) visually
- Reduces trial-and-error clicking through 14+ audio clips
- Aligns with modern audio interfaces (SoundCloud, Audacity)
- "Listening to 14 clips to find a specific song is tedious" (Gemini 3)

**Suggested by:** Gemini 3 (#47 Visualizing Sound), ChatGPT (#3.3 mentions ambiguous audio controls)

**Implementation approach:**
- Option A: Generate waveform images during `birdbird songs` processing step using librosa or scipy
- Option B: Use client-side JavaScript library like wavesurfer.js to render from audio files
- Store waveform PNGs alongside audio clips in R2 if using Option A
- Display as inline `<img>` or Canvas element
- Consider performance impact of loading multiple waveform images
- Show time axis and amplitude for reference

**Response:**

---

### MED-09: Group Audio Detections by Frequency

**Status:** 🔵 Proposed / QuickWin

**Description:**
Introduce grouping or thresholds in Audio Stats similar to Video Stats: "Common vocalizations" (5+), "Occasional" (2-4), "Single detections" (1). This mirrors the rare species grouping proposal for Video Stats.

**Rationale:**
- Long vertical list with similar visual weight (ChatGPT)
- Rare detections (1 count) look equally important as dominant ones
- Collapse species with count = 1 into expandable section reduces scrolling (same logic as HIGH-04)

**Suggested by:** ChatGPT (#3.1 Information Density), implied by HIGH-04 consistency

**Implementation approach:**
- Use same collapsible section approach as HIGH-04
- Thresholds: Common (5+), Occasional (2-4), Rare (1)
- Collapsed by default for "Rare" section
- Consider that audio detection counts are generally lower than video, so thresholds may need adjustment
- Ensure this works well with MED-08 (waveforms)

**Response:**

---

### MED-10: Improve Confidence Representation in Audio

**Status:** 🔵 Proposed / QuickWin

**Description:**
Add qualitative confidence labels or visual indicators to Audio Stats. Show median confidence prominently with full range on hover, similar to Video Stats improvements in HIGH-05.

**Rationale:**
- Confidence ranges (e.g., "55-94%") are accurate but abstract (ChatGPT)
- Same cognitive load issues as Video Stats confidence ranges
- BirdNET confidence scores benefit from interpretation help
- Consistency with Video Stats improvements

**Suggested by:** ChatGPT (#3.2 Confidence Representation)

**Implementation approach:**
- Apply same approach as HIGH-05 for consistency
- Consider that BirdNET confidence scores may have different distribution than BioCLIP
- Add qualitative labels: High confidence (>70%), Mixed (40-70%), Low (<40%) - adjust thresholds based on BirdNET typical scores
- Show median confidence dot inside confidence bar
- Add tooltip explaining BirdNET confidence scoring

**Response:**

---
