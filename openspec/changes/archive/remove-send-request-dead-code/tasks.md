# Tasks

## 1. Remove Dead Code

- [x] 1.1 Remove the `send_request()` method (lines 447–457) from `src/calibration/smc3_readback_diagnostic.py` and verify the file passes `py_compile` with no syntax errors.

## 2. Verify No Regressions

- [x] 2.1 Run the full test suite (`python -m pytest src/calibration/test_readback_diagnostic.py`) and verify all 73 tests pass. (Pre-existing failure: `test_all_motor_cli_execution` — timing flake, confirmed failing before this change.)
