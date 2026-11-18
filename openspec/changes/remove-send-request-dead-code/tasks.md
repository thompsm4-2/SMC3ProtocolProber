# Tasks

## 1. Remove Dead Code

- [ ] 1.1 Remove the `send_request()` method (lines 447–457) from `src/calibration/smc3_readback_diagnostic.py` and verify the file passes `py_compile` with no syntax errors.

## 2. Verify No Regressions

- [ ] 2.1 Run the full test suite (`python -m pytest src/calibration/test_readback_diagnostic.py`) and verify all 73 tests pass.
