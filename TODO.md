# birdbird - TODO

## Original Milestones

These milestones were defined at project start and tracked in README.md (since removed).  Noted here for historical reference as the numbered refs are mentioned in the commit history.

| #    | Milestone                  | Description                                                                                                                                                            | Status |
| ---- | -------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------ |
| M1   | Bird detection filter      | Discard clips without birds (eliminate wind false positives)                                                                                                           | Done   |
| M2   | Highlights reel v1         | Concatenate segments with bird activity                                                                                                                                | Done   |
| M2.1 | Highlights reel seek       | Based on M4 output, provide buttons to seek to timestamps with highest confidence for each species                                                                     | Done   |
| M2.2 | Publish highlights to web  | Upload to Cloudflare R2 with static web viewer showing video and audio stats                                                                                           | Done   |
| M3   | Highlight images           | Extract species-specific frames from M4 detections                                                                                                                     | Dropped |
| M4   | Visual species detection   | Identify species, generate timeline summary with frame capture                                                                                                         | Done   |
| M5   | Full report, stats         | Automated summary reports, expanding on M2.2 to showcase the M3/M4 material                                                                                           | Done    |


## Build / Safety Improvements

[x] add mypy as a pre-commit hook to check/enforce type hints (infrastructure ready, disabled pending fixes below)

### mypy Type Safety Roadmap

Phase 1: Fix existing type errors (14 errors across 6 files)
- [x] Fix filter.py:84 - Type mismatch (BirdbirdPaths assigned to int variable)
- [x] Fix highlights.py:189-194 - None safety for float values (4 errors)
- [x] Fix species.py:284 - tqdm iterator assigned to list[Path] variable
- [x] Fix species.py:538 - RemoteConfig None handling in RemoteProcessor
- [x] Fix songs.py:319 - Add type annotation for detections variable
- [x] Fix songs.py:566 - dict[str, float] assigned to float variable
- [x] Fix publish.py - File handle type mismatches (4 errors at lines 430, 464, 519, 551)
- [x] Fix frames.py:201 - Add type annotation for raw_scores variable

Phase 2: Enable mypy pre-commit hook
- [x] Uncomment mypy hook in .pre-commit-config.yaml
- [x] Verify all tests pass with mypy enabled

Phase 3: Increase strictness
- [x] Enable warn_return_any in pyproject.toml
- [x] Enable warn_unused_configs in pyproject.toml
- [x] Fix any new warnings

Phase 4: Maximum type safety (optional)
- [ ] Enable disallow_untyped_defs (require all functions have type hints)
- [ ] Enable strict mode for comprehensive type checking
- [ ] Consider removing module overrides once upstream stubs are available
