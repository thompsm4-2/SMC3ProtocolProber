# Tasks

## 1. Fix import path

- [x] 1.1 Change `sys.path.insert(0, "/home/mathomp/Documents/Development/MotionSimProjects/h3_wt901c_characterization_v0.1")` to `sys.path.insert(0, os.path.join(os.path.dirname(__file__)))` in `src/calibration/test_v04.py` line 9 and verify the file compiles with `python3 -m py_compile src/calibration/test_v04.py`

## 2. Fix test_tx_logger() for current API

- [x] 2.1 Update the `test_tx_logger()` function in `src/calibration/test_v04.py` to provide the required `run_start` argument to `TXLogger()` constructor (around line 159) and verify the test passes by running `python3 src/calibration/test_v04.py`

## 3. Verify full test suite

- [x] 3.2 Run `python3 src/calibration/test_v04.py` from the project root and verify all tests pass with exit code 0
- [x] 3.3 Run `python3 -m py_compile src/calibration/test_v04.py` to confirm no syntax errors

## Workflow follow-up

- Archive the change after review.
