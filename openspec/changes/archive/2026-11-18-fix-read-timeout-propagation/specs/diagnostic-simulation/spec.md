# Spec Delta

## MODIFIED Requirements

### Requirement: Simulate mode activates FakeSerial

The system SHALL replace the real `serial.Serial` connection with the existing `FakeSerial` class when the `--simulate` flag is provided. The `FakeSerial` instance SHALL be constructed with the same `--port`, `--baud`, `--read-timeout`, and `--write-timeout` values passed by the user. The `--read-timeout` value SHALL also control the response collection deadline used by `poll_motor()`: when `--read-timeout` is set to a value other than the default 0.10 s, the diagnostic SHALL wait for that many seconds for a readback response before timing out, regardless of whether the tool runs in `--simulate` mode or real-hardware mode.

#### Scenario: Simulate mode uses FakeSerial

- **WHEN** `--simulate` is passed to the diagnostic utility
- **THEN** the utility creates a `FakeSerial` instance instead of calling `serial.Serial`

#### Scenario: Simulate mode preserves serial parameters

- **WHEN** `--simulate` is passed along with `--port`, `--baud`, `--read-timeout`, and `--write-timeout`
- **THEN** the `FakeSerial` instance is constructed with those same parameter values
- **AND** `poll_motor()` uses the `--read-timeout` value as its response collection deadline

#### Scenario: Simulate mode respects custom read-timeout

- **WHEN** `--simulate --read-timeout 2.0 --simulate-count 1` is passed
- **THEN** `poll_motor()` waits up to 2.0 seconds for a response before timing out

#### Scenario: Real-hardware mode respects custom read-timeout

- **WHEN** `--port /dev/ttyACM0 --read-timeout 2.0 --motor A --duration 5` is passed
- **THEN** `poll_motor()` waits up to 2.0 seconds for a response before timing out
