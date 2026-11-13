# Tasks

## 1. Fix run_active() to transmit position commands

- [ ] 1.1 Replace `READ_COMMANDS[self.motor]` with `smc3_frame(self.motor, target)` in `run_active()` and verify the import resolves without circular dependency
- [ ] 1.2 Update `transmitted_hex` to be computed from the position-command bytes (not the readback query bytes) and verify CLI output shows correct hex for each target

## 2. Correct misleading comments and warnings

- [ ] 2.1 Remove or correct the inline comment "Send position command" that no longer describes the actual code, and verify the comment now accurately describes the position command being sent
- [ ] 2.2 Update any hardware warning text that references readback queries in the active test context, and verify the warning text is coherent with the new behavior

## 3. Add regression tests for exact transmitted bytes

- [ ] 3.1 Add a test that verifies `run_active()` transmits the exact SMC3 position-command bytes for each target in `ACTIVE_TEST_SEQUENCE` on motor A, and verify the test asserts on `bytes([91, 65, (target >> 8) & 255, target & 255, 93])` for each target
- [ ] 3.2 Add a test that verifies exact transmitted bytes for motor B and motor C, and verify the test asserts correct motor byte (0x42, 0x43) in the transmitted frame
- [ ] 3.3 Add a test that verifies position clamping (target < 0 clamps to 0, target > 1023 clamps to 1023) and verify the transmitted bytes match the clamped position

## 4. Verify existing tests still pass

- [ ] 4.1 Run the full test suite for `test_readback_diagnostic.py` and verify all existing tests pass after the change
- [ ] 4.2 Run the full test suite for `test_v04.py` and `test_fake_serial.py` and verify no regressions in unrelated tests
