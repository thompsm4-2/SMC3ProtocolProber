# Tasks

## 1. Remove dead attribute from FakeSerial

- [ ] 1.1 Remove `self.baudrate = baudrate` from `FakeSerial.__init__` in `src/calibration/smc3_readback_diagnostic.py` (line 80) and verify the file imports cleanly with `python -c "from src.calibration.smc3_readback_diagnostic import FakeSerial; print('OK')"`

## 2. Update test assertions

- [ ] 2.1 Remove `assert test_serial.baudrate == 500000` from `src/calibration/test_readback_diagnostic.py` (line 704) and verify the test file imports cleanly
- [ ] 2.2 Remove `assert fake_serial.baudrate == 500000` from `src/calibration/test_readback_diagnostic.py` (line 835) and verify the test file imports cleanly
- [ ] 2.3 Remove `assert factory_return_value[0].baudrate == 500000` from `src/calibration/test_readback_diagnostic.py` (line 1162) and verify the test file imports cleanly

## 3. Verify no regressions

- [ ] 3.1 Run the full test suite (`python -m pytest src/calibration/test_readback_diagnostic.py -v`) to confirm no pre-existing failures and no regressions from this change
- [ ] 3.2 Run `python -m pytest src/calibration/test_fake_serial.py -v` to confirm no regressions in the related FakeSerial test file
