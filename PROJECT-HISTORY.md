# Project History

## Timeline

| Date | Active Time | Summary |
|------|------------|---------|
| 2026-01-15 | 6 h | **Project kick-off** — initial commit, set up project structure, implemented bird detection filter and highlights reel, plus frame capture with quality scoring. |
| 2026-01-16 | 6.5 h | **Publishing pipeline** — added Cloudflare R2 publishing with web-optimised video output, hardware encoder detection, and documented the captions feature idea. |
| 2026-01-19 | 2 h | **Fixes and tidying** — fixed publish directory handling, corrected batch IDs to use data date, removed person detection, and integrated frames extraction into the process command. |
| 2026-01-20 | 2.5 h | **Web viewer + BirdNET** — added date range support and cosmetic improvements to the viewer, built the credits page, and added the `songs` command for BirdNET bird vocalization detection. |
| 2026-01-21 | 5.5 h | **Audio pipeline end-to-end** — integrated songs into the process pipeline, added an Audio tab to the viewer with species stats and audio clip players, fixed publish sync, and improved accessibility and mobile layout. |
| 2026-01-23 | 3 h | **Species ID design** — researched and documented the BioCLIP visual species identification approach with remote GPU support. |
| 2026-01-24 | 1.5 h | **Species ID implementation** — implemented visual species identification with remote GPU, added species.json publishing, and showed detected species in the viewer. |
| 2026-01-25 | 1 h | **Small improvements** — added proposed accessibility pre-commit check feature. |
| 2026-01-26 | ~0 h | **README** — updated and improved project README. |
| 2026-01-27 | 1 h | **Structural refactor** — refactored pipeline folder structure into working/assets separation. |
| 2026-01-28 | 5 h | **Viewer redesign + best clips** — implemented field guide aesthetic across viewer, added Video Stats tab, added best clips feature with species seek buttons, and collected/evaluated UX improvement proposals. |
| 2026-01-29 | 8.5 h | **Polish and tooling** — added method.html page, breadcrumb navigation, info overlays, favicon, local dev config system, pre-commit hooks (HTML/CSS/JS validation, pa11y accessibility, British English spellcheck). |
| 2026-01-30 | 4 h | **Testing and accessibility** — added the first comprehensive unit test suite, pytest pre-commit hook, improved web accessibility with semantic nav and focus indicators, and tidied up viewer layout. |
| 2026-02-02 | 0.5 h | **Bug fix** — fixed species command to use the new assets directory structure and auto-generate best_clips.json. |
| 2026-02-03 | 0.5 h | **Documentation** — added a comprehensive camera compatibility guide. |
| 2026-02-05 | 1.5 h | **Video UX** — paused video on tab switch, improved video loading UX, and fixed skip link and hover contrast issues. |
| 2026-02-11 | 3.5 h | **Code quality infrastructure** — added mypy type checking, bandit security analysis, pip-audit, fixed all type errors across 6 files, and added 72 Layer 2 mocked unit tests. |
| 2026-02-16 | 0.5 h | **Time estimation** — analysed session records and git history to produce this timeline. |
| **Total** | **~53 h** | |

---

## Methodology

### Data sources

Active time figures come from two sources:

1. **Claude session files** — `~/.claude/projects/-home-ross-src-birdbird/*.jsonl`
   Each file is one Claude Code conversation. Every message has a `timestamp` field.

2. **Git log** — `git log --format="%ai %s" --reverse`
   Used to identify what was worked on each day and to sanity-check session dates.

### How active time is calculated

Active time is computed with a **30-minute gap threshold**: consecutive message timestamps within the same session file that are more than 30 minutes apart are treated as idle (session left open, break, switched to another task) and the gap is not counted. Only the intervals between messages ≤ 30 minutes apart are summed.

This avoids inflating time for sessions left open overnight or across long breaks. The raw sum of session durations (first to last message, no gap filtering) was ~103 hours; the gap-filtered total is ~53 hours.

The script used:

```python
import os, json, glob
from datetime import datetime
from collections import defaultdict

directory = os.path.expanduser("~/.claude/projects/-home-ross-src-birdbird/")
files = sorted(glob.glob(os.path.join(directory, "*.jsonl")))

GAP_THRESHOLD_MINUTES = 30
total_active_minutes = 0
by_date = defaultdict(float)

for f in files:
    timestamps = []
    with open(f) as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
                ts = d.get("timestamp")
                if ts:
                    timestamps.append(datetime.fromisoformat(ts.replace('Z', '+00:00')))
            except:
                pass

    if len(timestamps) < 2:
        continue
    timestamps.sort()
    active_minutes = 0
    for i in range(1, len(timestamps)):
        gap = (timestamps[i] - timestamps[i-1]).total_seconds() / 60
        if gap <= GAP_THRESHOLD_MINUTES:
            active_minutes += gap
    by_date[timestamps[0].date().isoformat()] += active_minutes

for date in sorted(by_date):
    mins = by_date[date]
    print(f"{date}: {mins:.0f} min = {mins/60:.1f} h")
```

### How to update this file

When extending the timeline for a new working period:

1. Run the script above and note the new daily totals since the last entry.
2. Check `git log --format="%ai %s"` for the same date range to identify what was worked on.
3. Write one summary sentence per day, cross-referencing the commit messages.
4. Use the same gap threshold (30 minutes) for consistency.
5. Update the **Total** row at the bottom.

### Notes and caveats

- The 30-minute threshold is a judgement call. A shorter threshold (e.g. 15 min) would reduce the total further; a longer one would increase it. 30 minutes felt right given typical Claude response times for longer tasks.
- Sessions without any `timestamp` fields (older format) are excluded — these are a small minority.
- Work done outside Claude (manual edits, terminal work, reading docs) is not captured by the session files, but given that almost all project work went through Claude Code sessions, the figures are a reasonable proxy.
- The project started on **15 January 2026**.
