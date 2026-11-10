# Proposal

## Why

The `smc3_readback_diagnostic.py` utility currently requires hardware connected to run — its `main()` function accepts a `serial_factory` parameter for test injection, but there is no CLI flag to enable software-only simulation mode. Users who want to run the diagnostic without hardware, verify the tool's behavior, or generate sample output must write Python code to inject `FakeSerial`. Adding a `--simulate` flag closes this gap and makes the diagnostic tool usable in CI and documentation workflows.

## What Changes

- Add `--simulate` CLI flag to `smc3_readback_diagnostic.py`
  - When enabled, uses the existing `FakeSerial` class instead of `serial.Serial`
  - Skips the hardware confirmation prompt (unsafe operations are safe in simulation)
  - Skips serial device detection (no hardware to detect)
- Add `--simulate-response` CLI option (repeatable) to provide canned responses
  - Each invocation appends one response byte sequence in hex format (e.g., `--simulate-response "5B 72 64 41 5D"`)
  - Responses are consumed in FIFO order, one write → one response
  - If responses are exhausted, subsequent reads return empty (timeout behavior)
- Add `--simulate-count` CLI option to limit the number of simulated requests
  - Defaults to 10 (prevents infinite loops in passive mode)
  - Acts as a request counter, independent of `--duration`
  - `0` means unlimited in passive mode; in active-target-test mode, runs the full fixed sequence
- No changes to existing CLI flags, hardware paths, or production behavior
- `--port` is optional in simulate mode (no device detection or validation required)
- `--motor ALL` in simulate mode uses round-robin distribution across motors A, B, C
  - Note: real-hardware `--motor ALL` has a pre-existing `KeyError` bug (motor `"ALL"` is not a key in `READ_COMMANDS`); this feature does not fix that bug

## Capabilities

### New Capabilities

- `diagnostic-simulation`: Software-only diagnostic mode using `FakeSerial` with configurable canned responses, enabling hardware-free testing and validation of the SMC3 readback diagnostic utility.

### Modified Capabilities

None.

## Impact

- **Files Modified**:
  - `src/calibration/smc3_readback_diagnostic.py` (CLI flags and simulation routing)
  - `src/calibration/test_readback_diagnostic.py` (6 new unit tests)
- **Scope**: Adds CLI flags and simulation routing logic; no changes to `FakeSerial`, `DiagnosticSession`, or `ReadbackDiagnostic` classes
- **Dependencies**: None — uses existing `FakeSerial` class already in the module
- **Breaking Changes**: None
- **Backward Compatibility**: Fully preserved — all existing flags and behavior unchanged
- **Known Pre-existing Bug Not Fixed**: `--motor ALL` on real hardware raises `KeyError` because `"ALL"` is not a key in `READ_COMMANDS`; simulation mode handles `ALL` with round-robin distribution but does not fix the real-hardware bug
