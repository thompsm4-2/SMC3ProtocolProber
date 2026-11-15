# Design

## Context

`ReadbackDiagnostic.run_active()` in `src/calibration/smc3_readback_diagnostic.py` currently sends `READ_COMMANDS[self.motor]` (a readback query like `[rdA]`) for every target in the active test. The test is intended to command the platform to move to each target position and then verify the platform settled by polling readback. The bug means the platform never receives a position command, so the test produces meaningless results.

The position command encoding is already implemented in `h3_characterize.py` as `smc3_frame(motor, position)`, documented in `specs/sm02_motor_command_protocol.md`, and tested in `test_fake_serial.py`. The function takes a motor letter (A/B/C) and a position (0–1023, clamped), and returns a 5-byte SMC3 frame.

## Goals / Non-Goals

**Goals:**
- Fix `run_active()` to transmit position commands using `smc3_frame()` encoding.
- Ensure `transmitted_hex` accurately reflects the position-command bytes.
- Correct misleading comments and hardware warning text.
- Add regression tests verifying exact transmitted bytes.

**Non-Goals:**
- Do not change `READ_COMMANDS` capitalization (uppercase vs lowercase).
- Do not modify passive mode or any other diagnostic behavior.
- Do not broaden into protocol-documentation cleanup.
- Do not modify unrelated or stale specification content.

## Decisions

### Decision: Import and use `smc3_frame` from `h3_characterize.py`

`smc3_frame(motor, position)` already exists in `h3_characterize.py` and implements the correct SMC3 position command encoding. Importing it avoids duplicating the frame-construction logic.

**Alternatives considered:**
1. **Inline the frame construction** in `run_active()` — rejected to avoid code duplication and potential drift from the canonical implementation.
2. **Move `smc3_frame()` into `smc3_readback_diagnostic.py`** — rejected; the canonical location is `h3_characterize.py` and importing preserves a single source of truth.

### Decision: Clamp positions using the same bounds as `smc3_frame()`

`smc3_frame()` clamps positions to `MIN_POS` (0) and `MAX_POS` (1023). The fix should delegate clamping to `smc3_frame()` rather than implementing separate bounds logic.

## Risks / Trade-offs

| Risk | Mitigation |
|------|-----------|
| Importing `smc3_frame` from `h3_characterize.py` could introduce a circular import if `smc3_readback_diagnostic.py` is imported by `h3_characterize.py` | Verify import chain before applying; if circular, inline the frame construction as a fallback. |
| Position clamping behavior could differ if `smc3_frame()` bounds change | Use `smc3_frame()` directly so clamping is always consistent. |
| Regression tests need to match exact byte sequences | Tests will assert on specific byte arrays for known targets, catching any encoding drift. |

## Migration Plan

This is a bug fix with no migration steps. The fix replaces incorrect behavior with correct behavior. Existing CSV output format is preserved; only the `transmitted_hex` values will differ (now showing actual position-command bytes).

## Open Questions

None. The fix is narrowly scoped to the active test's command transmission.
