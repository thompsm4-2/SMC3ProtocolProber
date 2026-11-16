# smc3-readback-commands Specification

## Purpose
Defines the correct byte encoding for SMC3 readback request commands sent to the controller, establishing that uppercase motor identifiers are required per the November 14, 2026 H3 readback investigation.

## Requirements

### Requirement: Readback commands use uppercase motor identifiers

The system SHALL encode SMC3 readback request commands with uppercase motor identifiers (`[rdA]`, `[rdB]`, `[rdC]`) in all tools that send readback requests to the controller. The command byte sequence for each motor is defined as:

- **Motor A**: `0x5B 0x72 0x64 0x41 0x5D` → `b"[rdA]"`
- **Motor B**: `0x5B 0x72 0x64 0x42 0x5D` → `b"[rdB]"`
- **Motor C**: `0x5B 0x72 0x64 0x43 0x5D` → `b"[rdC]"`

#### Scenario: Motor A readback command encoding

- **WHEN** a tool constructs a readback request for motor A
- **THEN** the command bytes are exactly `b"[rdA]"` (hex: `5B 72 64 41 5D`)

#### Scenario: Motor B readback command encoding

- **WHEN** a tool constructs a readback request for motor B
- **THEN** the command bytes are exactly `b"[rdB]"` (hex: `5B 72 64 42 5D`)

#### Scenario: Motor C readback command encoding

- **WHEN** a tool constructs a readback request for motor C
- **THEN** the command bytes are exactly `b"[rdC]"` (hex: `5B 72 64 43 5D`)

#### Scenario: Lowercase motor identifiers are not used

- **WHEN** a tool constructs a readback request for any motor
- **THEN** the command bytes must not contain lowercase motor letters (`a`, `b`, `c` at byte offset 3)

#### Scenario: READ_COMMANDS dictionary is consistent across tools

- **WHEN** `h3_characterize.py` and `smc3_readback_diagnostic.py` both define `READ_COMMANDS`
- **THEN** both tools produce identical byte sequences for each motor key
