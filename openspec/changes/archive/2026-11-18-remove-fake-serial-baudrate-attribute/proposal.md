# Proposal

## Why

`FakeSerial` in `smc3_readback_diagnostic.py` stores a `baudrate` attribute in `__init__` that is never read by any method in the class. This is dead code that adds unnecessary state to the test mock and misleads readers into thinking the baudrate affects FakeSerial behavior.

## What Changes

- Remove `self.baudrate = baudrate` from `FakeSerial.__init__` in `src/calibration/smc3_readback_diagnostic.py`.
- Update three test assertions in `src/calibration/test_readback_diagnostic.py` that check `fake_serial.baudrate` to remove those assertions (the tests still verify port and timeout, which are the only attributes FakeSerial actually uses).

## Capabilities

_(none — this is a pure code quality fix with no behavioral or spec-level changes)_

## Impact

| Area | Details |
|------|---------|
| **Code** | `src/calibration/smc3_readback_diagnostic.py` — one line removed from `FakeSerial.__init__` (line 80) |
| **Tests** | `src/calibration/test_readback_diagnostic.py` — three assertions removed (lines 704, 835, 1162) |
| **Behavior** | None. The `baudrate` parameter is still accepted by `FakeSerial.__init__` (for API compatibility with `serial.Serial`), it is simply not stored. |
| **Risk** | Minimal — removes one unused attribute. All other FakeSerial behavior is unchanged. Tests that verify port and timeout remain intact. |
