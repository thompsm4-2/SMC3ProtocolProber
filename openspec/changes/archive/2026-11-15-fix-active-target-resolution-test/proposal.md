# Proposal

## Why

`ReadbackDiagnostic.run_active()` transmits a readback query (`[rdA]`, `[rdB]`, or `[rdC]`) for every target instead of a position command. The active target-resolution test therefore never commands the advertised positions, and its CLI output and CSV associate target values with readback-query bytes rather than the actual position commands that should have been sent.

## What Changes

- Replace `READ_COMMANDS[self.motor]` with a position command built via the established `smc3_frame()` encoding for each target value.
- Update `transmitted_hex` to show the actual position-command bytes sent.
- Correct the misleading comment ("Send position command") and the hardware warning to reflect that a position command is now transmitted.
- Add regression tests that verify the exact transmitted bytes for each target and motor.

## Capabilities

### New Capabilities

- **diagnostic-active-test**: Defines the correct behavior of the active target-resolution test — each step must transmit a position command for the requested target using `smc3_frame()`, then poll readback to verify the platform settled.

### Modified Capabilities

<!-- None — existing spec requirements are not being changed. -->

## Impact

- **Affected code**: `src/calibration/smc3_readback_diagnostic.py` — `ReadbackDiagnostic.run_active()` method, `transmitted_hex` computation, inline comments, and hardware warning text.
- **Affected tests**: `src/calibration/test_readback_diagnostic.py` — add regression tests verifying exact transmitted bytes for each target/motor combination.
- **No changes to**: `READ_COMMANDS` capitalization, passive mode, readback decoding, or any other diagnostic behavior.
