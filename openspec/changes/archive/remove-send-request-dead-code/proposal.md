# Proposal

## Why

The `send_request()` method in `src/calibration/smc3_readback_diagnostic.py` (line 447) is dead code — it is defined but never called anywhere in the codebase. It returns a misleading `(b"", written)` tuple that suggests a response was received when in fact no response data is returned. Removing it eliminates confusion for future maintainers and cleans up the codebase.

## What Changes

- **Remove** the `send_request()` method (lines 447–457) from `src/calibration/smc3_readback_diagnostic.py`.
- No behavioral change. No API change. No test changes needed.

## Capabilities

No capabilities are added or modified. This is a pure code cleanup with zero behavioral impact.

## Impact

- **Files affected:** `src/calibration/smc3_readback_diagnostic.py` (one method removed, ~10 lines)
- **Risk:** None — the method has zero callers in the entire codebase, confirmed by exhaustive grep across all Python, test, config, and documentation files.
