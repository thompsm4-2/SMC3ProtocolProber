# Tasks

## 1. Fix _cleanup() method

- [x] 1.1 Replace `self.serial._closed` with `getattr(self.serial, 'closed', getattr(self.serial, '_closed', True))` in `DiagnosticSession._cleanup()` and verify the file parses without syntax errors
- [x] 1.2 Replace `self._diagnostic.serial._closed` with the same `getattr` pattern for the diagnostic's serial reference and verify the file parses without syntax errors

## 2. Verify with existing tests

- [x] 2.1 Run the full existing test suite (`pytest src/calibration/test_readback_diagnostic.py`) and verify all tests pass, including `test_cleanup_on_error` and all tests that call `session._cleanup()`

## 3. Add regression test for real pySerial behavior

- [x] 3.1 Add a test that uses a mock object with a public `closed` attribute (simulating real pySerial `Serial`) and verify `_cleanup()` handles it without `AttributeError`
- [x] 3.2 Add a test that sets `session.serial = None` and verify `_cleanup()` returns without error

## Workflow follow-up

- Archive the change after the project's review requirements are satisfied.
- Verify the archived result.
