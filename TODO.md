# birdbird - TODO

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
