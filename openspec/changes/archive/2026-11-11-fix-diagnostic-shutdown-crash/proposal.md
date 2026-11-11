# Proposal

## Why

`DiagnosticSession._cleanup()` accesses `self.serial._closed` to check whether the serial connection is closed before attempting to close it. The `FakeSerial` test stub exposes a `_closed` attribute, so tests pass. However, real pySerial `serial.Serial` objects expose `closed` (not `_closed`), so running the diagnostic with real hardware causes an `AttributeError` during shutdown. The diagnostic crashes when trying to clean up serial resources, even when the serial connection is already closed.

## What Changes

- Fix `DiagnosticSession._cleanup()` to use the public `closed` attribute (pySerial API) instead of the private `_closed` attribute.
- Ensure `_cleanup()` works correctly with both real `serial.Serial` objects and the `FakeSerial` test stub without breaking existing tests.
- Add a spec for diagnostic shutdown and cleanup behavior.

## Capabilities

### New Capabilities

- **diagnostic-cleanup**: Defines the expected shutdown and resource cleanup behavior for `DiagnosticSession`, including safe serial port closure when the connection is already closed or when `self.serial` is `None`.

### Modified Capabilities

<!-- None — this is a new capability, not a modification of existing specs. -->

## Impact

- **Affected code**: `src/calibration/smc3_readback_diagnostic.py` — `DiagnosticSession._cleanup()` method (lines 211–224)
- **Affected tests**: `src/calibration/test_readback_diagnostic.py` — multiple tests that call `session._cleanup()` and assert on `ser._closed`
- **No API changes**: The public interface of `DiagnosticSession` is unchanged.
- **No new dependencies**: Pure Python fix using existing pySerial attributes.
