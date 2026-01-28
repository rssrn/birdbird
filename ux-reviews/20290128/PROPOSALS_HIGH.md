# BirdBird UX Improvement Proposals - High Priority

## Status Legend
- 🔵 Proposed - awaiting decision
- ✅ Accepted - approved for implementation
- ❌ Rejected - declined

---

## Global / Cross-View

### HIGH-01: Add Period Summary Card

**Status:** 🔵 Proposed

**Description:**
Add a summary card at the top of each view showing key metrics for the selected date range: total species detected, most common species, any first-time/rare sightings, and audio-only detections count.

**Rationale:**
- Dramatically improves first-time comprehension (ChatGPT: "Very High Impact")
- Provides immediate "bird's-eye view" before diving into detailed stats
- Helps users quickly understand "what happened today" without scrolling through all data
- Creates narrative context that turns data into insight
- Addresses cognitive load concerns raised by all three AI reviews

**Suggested by:** ChatGPT (Strategic Enhancement #7.1), Gemini 3 (Overview card), Claude Opus 4.5 (implicit in framing concerns)

**Implementation approach:**
- Create summary component that appears above tabs or at top of each tab
- Calculate metrics: unique species count, top species by detection count, new species (first appearance in date range)
- Consider showing "Audio-only: N species" to highlight off-camera detections
- Example format: "14 species detected · Most common: Blue Tit · New this period: Marsh Tit · 8 audio-only"
- Could be a prominent card with icons for visual appeal
- Update calculation in publish.py when generating latest.json

**Response:**

---

### HIGH-02: Add Contextual Framing for Detection Counts

**Status:** 🔵 Proposed

**Description:**
Add context at the top of Video Stats and Audio Stats showing the denominator: "234 motion clips analysed · 312 total detections" or "498 clips analysed · 87 audio detections in 42 clips".

**Rationale:**
- "115 Blue Tit detections" sounds impressive but lacks context (ChatGPT #4.1)
- Users don't know if this is over 10 clips or 1000 clips, 1 hour or 24 hours
- Helps users understand detection density and reliability
- Provides scale for interpreting the numbers

**Suggested by:** ChatGPT (#4.1 Counts Without Context)

**Implementation approach:**
- Add summary line above species lists in Video Stats and Audio Stats
- For Video Stats: total clips processed, total detection count across all species
- For Audio Stats: total clips analysed, total vocalizations detected, number of clips with audio
- Source data from detections.json and songs.json
- Example: "Analysed 234 clips (2h 15m) · Found 312 bird detections"

**Response:**

---

### HIGH-03: Improve Cross-View Species Linking

**Status:** 🔵 Proposed

**Description:**
Enable navigation between related species detections across views. If a Blue Tit appears in Video Stats, show an indicator that it was also heard in Audio Stats, with a link to jump to that species in the other view.

**Rationale:**
- Currently audio and video stats are siloed (Claude Opus 4.5)
- Users want to know "What did I see vs. what did I hear?" (Gemini 3)
- Creates a more cohesive story of each bird's visit
- Helps users discover the full picture of species presence

**Suggested by:** Claude Opus 4.5 (Cross-referencing), Gemini 3 (Audio/Video Comparison), ChatGPT (implicit in data relationship concerns)

**Implementation approach:**
- Add small icon/badge next to species name in Video Stats if that species also appears in Audio Stats
- Add similar icon in Audio Stats if species appears in Video Stats
- Make icons clickable to jump to corresponding tab + scroll to that species
- Example: "Blue Tit 🔊" (has audio) or "Common Wood-Pigeon 👁️" (has video)
- Requires matching species names between BioCLIP and BirdNET outputs

**Response:**

---

## Video Stats View

### HIGH-04: Group Rare Species Detections

**Status:** 🔵 Proposed

**Description:**
Collapse or group species with only 1-2 detections into an expandable "Rare Visitors" or "Also Detected" section. This reduces the long tail of single-detection species that creates excessive scrolling and visual noise.

**Rationale:**
- Reduces cognitive load by de-emphasizing low-confidence, single-occurrence data
- Improves scannability by making dominant species more prominent
- Multiple reports (ChatGPT, Claude Opus, Gemini) identified this as the "long tail problem"
- Users likely care most about frequent visitors; rare sightings can still be accessible via expansion
- Several species with 1 detection at 51-65% confidence may be noise rather than signal

**Suggested by:** ChatGPT (#4.2, #3.1), Claude Opus 4.5 (#24), Gemini 3 (#3, Priority Win #3) - consensus across all three AI reviews

**Implementation approach:**
- Add threshold logic (e.g., count <= 2 or count < 3)
- Create collapsible `<details>` section with summary text (e.g., "5 rare species (1-2 detections each) - click to expand")
- Consider separate treatment for low-confidence (<60%) vs high-confidence rare detections
- Update both Video Stats and Audio Stats views in index.html
- Collapsed by default, remembers state in localStorage

**Response:**

---

### HIGH-05: Simplify Confidence Range Display

**Status:** 🔵 Proposed

**Description:**
Replace percentage ranges (e.g., "53-100%") with simpler confidence visualization: show median confidence with min/max on hover, or use qualitative labels (High/Medium/Low confidence).

**Rationale:**
- Ranges like "53-100%" are technically accurate but cognitively noisy (ChatGPT #4.3)
- Creates visual clutter that competes with the more important detection counts
- Users care more about "Was this definitely a Blue Tit?" than mathematical ranges
- Confidence tiers already used in Highlights view (Very Probable/Probable/Possible) but not in stats views

**Suggested by:** ChatGPT (#4.3, #3.2), Claude Opus 4.5 (#15), Gemini 3 (#40)

**Implementation approach:**
- Option A: Show median confidence prominently, display full range on hover/tooltip
- Option B: Use qualitative labels (⭐⭐⭐ High, ⭐⭐ Medium, ⭐ Low confidence)
- Option C: Visual indicator within the bar itself (gradient or opacity variation)
- Option D: Align with Highlights view tiers (Very Probable >80%, Probable 60-80%, Possible <60%)
- Update CSS to make confidence less prominent than count
- Consider adding small info icon with tooltip explaining confidence

**Response:**

---

## Highlights View

### HIGH-06: Add Video Context Header

**Status:** 🔵 Proposed

**Description:**
Add a prominent context header above the video player showing the current species, confidence, date/time, and other key metadata instead of requiring users to expand "Batch Information" accordion.

**Rationale:**
- Video currently appears without enough explanatory framing (ChatGPT #5.2)
- Date/time stamp is baked into video feed and hard to read (Gemini 3)
- "Batch Information" is hidden but likely contains important context (Claude Opus 4.5, Gemini 3)
- Users need to understand what they're watching before hitting play

**Suggested by:** ChatGPT (#5.2), Gemini 3 (#26), Claude Opus 4.5 (#38)

**Implementation approach:**
- Add header above video player with format: "Blue Tit · 94% confidence · 26 Jan, 09:14 · 12s clip"
- Surface key metadata inline: species name (large), confidence tier badge, timestamp, clip duration
- Remove or de-emphasize the collapsed "Batch Information" accordion
- Consider adding detection method indicator (e.g., "Visual detection via BioCLIP")
- Update when user clicks different species in sidebar

**Response:**

---

## Audio Stats View

### HIGH-07: Clarify Audio Control Purpose

**Status:** 🔵 Proposed

**Description:**
Add tooltips to audio playback controls and improve their visual prominence. Make it clear these buttons play actual bird vocalizations captured off-camera.

**Rationale:**
- Playback controls are small and their purpose isn't entirely clear (Claude Opus 4.5)
- Icons (play, waveform, speaker, menu) are compact but ambiguous (ChatGPT #3.3)
- This is "a lovely feature that deserves more prominence" (Claude Opus 4.5)
- Users may not realize they can hear the actual bird calls

**Suggested by:** ChatGPT (#3.3 Audio Controls), Claude Opus 4.5 (#17)

**Implementation approach:**
- Add aria-labels and visible tooltips on hover (e.g., "Play vocalization", "View spectrogram")
- Increase clickable area around small icons
- Consider consolidating controls (e.g., merge play + waveform into single "Play with visualization" button)
- Highlight which clip is the "best example" (highest confidence or clearest audio)
- Use customized player styling to match site aesthetic instead of default browser controls

**Response:**

---
