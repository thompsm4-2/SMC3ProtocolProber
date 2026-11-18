# Proposal

## Why

`test_v04.py` imports `h3_characterize` from an external project path (`/home/mathomp/Documents/Development/MotionSimProjects/h3_wt901c_characterization_v0.1`) that belongs to an earlier project iteration. This creates a fragile dependency on an unrelated project's codebase, makes the test non-portable, and means the test exercises an old version of `h3_characterize.py` (with lowercase read commands `[rda]`/`[rdb]`/`[rdc]`) instead of the current version (with uppercase `[rdA]`/`[rdB]`/`[rdC]`).

## What Changes

- **Change** the `sys.path.insert()` in `src/calibration/test_v04.py` (line 9) from the external project path to the local `src/calibration` directory, so the test imports from the current project's `h3_characterize.py`.
- **Update** the `test_tx_logger()` function to match the current `TXLogger` constructor signature, which now requires a `run_start` parameter (previously the external v0.4 module had a different signature).
- **Verify** that all other tests in `test_v04.py` pass against the current `h3_characterize.py` module.

## Capabilities

_No capabilities are created or modified. This is a pure test maintenance fix._

## Impact

- **Files modified:** `src/calibration/test_v04.py` (line 9 import path; line 159 test assertion for `TXLogger`)
- **No changes** to production code, API, or dependencies.
- **No CI/CD impact** — `test_v04.py` is a standalone legacy test file, not part of any test discovery pipeline.
