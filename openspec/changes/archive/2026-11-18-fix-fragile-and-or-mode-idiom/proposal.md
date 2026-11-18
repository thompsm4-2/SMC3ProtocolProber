# Proposal

## Why

The `smc3_readback_diagnostic.py` module uses the fragile `and`/`or` idiom (`x and "A" or "B"`) to select mode strings in two locations. While this idiom works correctly when `"ACTIVE"` is truthy, it would silently produce incorrect results if a future mode name were falsy (e.g., empty string, `0`, or `None`). Replacing it with a proper ternary eliminates this latent defect and aligns the code with the correct ternary pattern already used elsewhere in the same file.

## What Changes

- Replace `args.active_target_test and "ACTIVE" or "PASSIVE"` with `"ACTIVE" if args.active_target_test else "PASSIVE"` at two locations in `src/calibration/smc3_readback_diagnostic.py` (lines 1176 and 1355).
- **No behavioral change.** The ternary produces identical output for all valid inputs.

## Capabilities

No spec-level behavior changes. This is a pure code quality improvement.

## Impact

- **Affected file:** `src/calibration/smc3_readback_diagnostic.py` (2 lines)
- **Tests:** None assert on `stats["mode"]`; no test changes required.
- **Dependencies:** None.
