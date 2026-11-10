# diagnostic-simulation Specification

## Purpose

Enables software-only diagnostic mode for the SMC3 readback diagnostic utility using configurable canned responses, so the tool can be exercised without hardware connected.

## Requirements

### Requirement: Simulate mode activates FakeSerial

The system SHALL replace the real `serial.Serial` connection with the existing `FakeSerial` class when the `--simulate` flag is provided.

#### Scenario: Simulate mode uses FakeSerial

- **WHEN** `--simulate` is passed to the diagnostic utility
- **THEN** the utility creates a `FakeSerial` instance instead of calling `serial.Serial`

#### Scenario: Simulate mode preserves serial parameters

- **WHEN** `--simulate` is passed along with `--port`, `--baud`, `--read-timeout`, and `--write-timeout`
- **THEN** the `FakeSerial` instance is constructed with those same parameter values

### Requirement: Canned responses are consumed in FIFO order

The system SHALL deliver canned responses to the diagnostic in the order they were specified via `--simulate-response`, one response per serial write operation.

#### Scenario: First response for first write

- **WHEN** the user provides `--simulate-response "5B 72 64 41 5D"` and the diagnostic sends one readback request
- **THEN** the `FakeSerial` read returns the bytes `[rdA]` (hex `5B 72 64 41 5D`)

#### Scenario: Second response for second write

- **WHEN** the user provides two `--simulate-response` values and the diagnostic sends two readback requests
- **THEN** the first read returns the first response and the second read returns the second response

#### Scenario: Empty read when responses exhausted

- **WHEN** the user provides fewer `--simulate-response` values than serial write operations
- **THEN** subsequent reads return empty bytes, producing timeout behavior

### Requirement: Simulate count limits requests

The system SHALL limit the number of simulated serial write operations when `--simulate-count` is specified.

#### Scenario: Simulate count stops after N requests

- **WHEN** `--simulate-count 5` is passed in passive mode
- **THEN** the diagnostic sends exactly 5 readback requests and then stops

#### Scenario: Zero simulate count means unlimited

- **WHEN** `--simulate-count 0` is passed in passive mode
- **THEN** the diagnostic runs without a request count limit (existing behavior for `--duration 0`)
- **WHEN** `--simulate-count 0` is passed in active-target-test mode
- **THEN** the diagnostic runs through the full fixed target sequence (no early termination)

#### Scenario: Default simulate count is 10

- **WHEN** `--simulate` is passed without `--simulate-count`
- **THEN** the diagnostic stops after 10 requests

### Requirement: Request count is independent of duration

The system SHALL track `--simulate-count` as an independent request counter, not mapped to `--duration`. The passive mode loop stops when the request counter reaches `--simulate-count`, regardless of elapsed time.

#### Scenario: Request count limits regardless of duration

- **WHEN** `--simulate --simulate-count 3 --duration 300` is passed in passive mode
- **THEN** the diagnostic sends exactly 3 readback requests and stops, even though `--duration` would allow 300 seconds

### Requirement: Simulate mode skips hardware prompts

The system SHALL skip the hardware confirmation prompt and serial device detection when `--simulate` is enabled.

#### Scenario: No confirmation prompt in simulate mode

- **WHEN** `--simulate` is passed with `--active-target-test`
- **THEN** the utility proceeds directly to simulation without asking for user confirmation

#### Scenario: No device detection in simulate mode

- **WHEN** `--simulate` is passed without `--port`
- **THEN** the utility does not attempt to enumerate serial devices and does not error

### Requirement: Simulate mode does not write diagnostic files to disk

The system SHALL skip creating diagnostic output files (CSV logs, raw logs, summary files, and output directories) when `--simulate` is enabled. Other files on the system are unaffected.

#### Scenario: No output files in simulate mode

- **WHEN** `--simulate` is passed with `--output-dir /tmp/test`
- **THEN** no diagnostic output files (CSV logs, raw logs, summary files) are created in the configured `--output-dir`

### Requirement: Simulate mode preserves output

The system SHALL print a summary of simulated results to stdout when `--simulate` is enabled, replacing the summary file that would be written in hardware mode.

#### Scenario: Summary printed to stdout

- **WHEN** `--simulate` mode completes
- **THEN** the utility prints a summary to stdout showing total requests, successful responses, and timeouts

### Requirement: Simulate mode is additive to existing flags

The system SHALL accept `--simulate` alongside all existing CLI flags without conflict.

#### Scenario: Simulate with existing motor selection

- **WHEN** `--simulate --motor A --simulate-count 3` is passed
- **THEN** the diagnostic simulates 3 readback requests for motor A only

#### Scenario: Simulate with ALL motors (round-robin)

- **WHEN** `--simulate --motor ALL --simulate-count 6` is passed
- **THEN** the diagnostic simulates 6 readback requests distributed round-robin across motors A, B, C (A, B, C, A, B, C)
- **THEN** each motor receives exactly 2 requests (6 / 3 = 2)
- **Note**: This round-robin behavior is simulation-only. Real-hardware `--motor ALL` has a pre-existing `KeyError` bug (`"ALL"` is not a key in `READ_COMMANDS`); this feature does not fix that bug.
