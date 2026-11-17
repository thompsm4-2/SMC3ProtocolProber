# Proposal

## Why

The `send_command()` function in `h3_characterize.py` contains a duplicate `written = None` assignment on consecutive lines (lines 220–221). This is dead code that serves no purpose and may confuse future maintainers into believing the assignment is intentional (e.g., a reset after a code path). While it has zero runtime impact, removing it improves code clarity and aligns with the project's code quality standards.

## What Changes

- Remove one of the two identical `written = None` assignments in `send_command()` at line 221 of `src/calibration/h3_characterize.py`.
- No behavioral changes — the remaining `written = None` on line 220 is the only assignment before `written = ser.write(command)` on the next line.

## Capabilities

No capabilities are created or modified. This is a pure code-quality fix with no spec-level behavior changes.

## Impact

- **Affected file:** `src/calibration/h3_characterize.py`, line 221 (single line removal).
- **No API changes.** No test changes required. No dependency changes.
