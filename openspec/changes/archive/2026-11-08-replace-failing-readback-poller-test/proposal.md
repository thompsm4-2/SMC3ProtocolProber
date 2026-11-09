# Proposal

## Why

The `test_readback_poller()` test in `src/calibration/test_v04.py` is failing due to an API mismatch with the updated `TXLogger` class. Additionally, the test lacks comprehensive coverage of the synchronous `ReadbackPoller` implementation. This change replaces the failing test with five well-structured tests that cover the actual behavior of `ReadbackPoller`.

## What Changes

- Replace the existing failing `test_readback_poller()` test
- Create five new tests covering:
  - Context manager entry and exit, including CSV log creation and file closure
  - Successful `poll_motor()` operation with valid responses
  - `poll_motor()` timeout when `FakeSerial` provides no response
  - `poll_due()` polling interval behavior using deterministic timing
  - `poll_now()` immediate polling of all requested motors
- Use the existing `FakeSerial` implementation as-is

## Capabilities

### New Capabilities

None - this is a test-only change with no new system capabilities.

### Modified Capabilities

None - this change does not modify any existing system behavior requirements.

## Impact

- **Files Modified**: `src/calibration/test_v04.py` only
- **Scope**: Test file changes only; no production code modifications
- **Dependencies**: Uses existing `FakeSerial` and `ReadbackPoller` implementations
- **Breaking Changes**: None - only replaces a failing test
- **Backward Compatibility**: The new tests provide better coverage and are more deterministic
