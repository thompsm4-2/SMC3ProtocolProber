# Tasks

## 1. Fix READ_COMMANDS encoding in h3_characterize.py

- [x] 1.1 Change the three byte literals in `READ_COMMANDS` in `src/calibration/h3_characterize.py` from lowercase to uppercase motor identifiers (Motor A: `97→65`, Motor B: `98→66`, Motor C: `99→67`) and verify the file imports cleanly with `python -c "from src.calibration.h3_characterize import READ_COMMANDS; print(READ_COMMANDS)"`

## 2. Add regression test

- [x] 2.1 Create `src/calibration/test_h3_characterize.py` with a test function that imports `READ_COMMANDS` from `h3_characterize.py` and asserts the three values equal `b"[rdA]"`, `b"[rdB]"`, and `b"[rdC]"` respectively, and verify the test runs and passes with `python -m pytest src/calibration/test_h3_characterize.py -v`

## 3. Verify no regressions

- [x] 3.1 Run the existing test suite (`python -m pytest src/calibration/test_readback_diagnostic.py -v` and `python -m pytest src/calibration/test_fake_serial.py -v`) to confirm no pre-existing failures are introduced by this change, and report any pre-existing failures separately
