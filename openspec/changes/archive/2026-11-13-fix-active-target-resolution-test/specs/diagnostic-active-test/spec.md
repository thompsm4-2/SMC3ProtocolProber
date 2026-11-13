# Spec Delta

## Purpose

Defines the correct behavior of the active target-resolution test: each step must transmit a position command for the requested target using the established `smc3_frame()` encoding, then poll readback to verify the platform settled.

## ADDED Requirements

### Requirement: Active test transmits position command for each target

When `ReadbackDiagnostic.run_active()` iterates over the target list, it SHALL construct a position command for each target using the `smc3_frame(motor, position)` encoding defined in `specs/sm02_motor_command_protocol.md` (frame format `[<motor><high><low>]`) and transmit that command to the serial port.

#### Scenario: Position command sent for target 512 on motor A

- **GIVEN** `run_active()` is called with `motor="A"` and `targets=[512]`
- **THEN** the serial write transmits `bytes([91, 65, 2, 128, 93])` (`[A\x02\x80]`), the SMC3 position command for motor A at position 512

#### Scenario: Position command sent for target 0 on motor B

- **GIVEN** `run_active()` is called with `motor="B"` and `targets=[0]`
- **THEN** the serial write transmits `bytes([91, 66, 0, 0, 93])` (`[B\x00\x00]`), the SMC3 position command for motor B at position 0

#### Scenario: Position command sent for target 1023 on motor C

- **GIVEN** `run_active()` is called with `motor="C"` and `targets=[1023]`
- **THEN** the serial write transmits `bytes([91, 67, 4, 255, 93])` (`[C\x04\xff]`), the SMC3 position command for motor C at position 1023

#### Scenario: Position command clamped to valid range

- **GIVEN** `run_active()` is called with `motor="A"` and `targets=[-10]`
- **THEN** the transmitted position command uses position `0` (clamped to MIN_POS), transmitting `bytes([91, 65, 0, 0, 93])`

#### Scenario: Position command clamped to maximum

- **GIVEN** `run_active()` is called with `motor="A"` and `targets=[2000]`
- **THEN** the transmitted position command uses position `1023` (clamped to MAX_POS), transmitting `bytes([91, 65, 4, 255, 93])`

### Requirement: transmitted_hex reflects the position command bytes

The `transmitted_hex` value logged in the active test CSV and printed to the CLI SHALL be the hex representation of the position command bytes actually transmitted, not the readback query bytes.

#### Scenario: transmitted_hex shows position command for target 512

- **GIVEN** `run_active()` transmits `bytes([91, 65, 2, 128, 93])` for target 512 on motor A
- **THEN** `transmitted_hex` is `"5B 41 02 80 5D"`

#### Scenario: transmitted_hex shows position command for target 0

- **GIVEN** `run_active()` transmits `bytes([91, 66, 0, 0, 93])` for target 0 on motor B
- **THEN** `transmitted_hex` is `"5B 42 00 00 5D"`

### Requirement: Active test preserves readback polling

After transmitting the position command and waiting for the settling delay, `run_active()` SHALL poll the motor for a readback response using the existing `poll_motor()` method.

#### Scenario: Readback polled after position command

- **GIVEN** `run_active()` transmits a position command and waits `settling_delay` seconds
- **THEN** `poll_motor(DEFAULT_TIMEOUT, 0.05)` is called to query the readback response

#### Scenario: Readback results logged with correct target

- **GIVEN** `run_active()` transmitted position 512 and received a valid readback response
- **THEN** `log_active_test()` is called with `target=512` and the decoded readback values
