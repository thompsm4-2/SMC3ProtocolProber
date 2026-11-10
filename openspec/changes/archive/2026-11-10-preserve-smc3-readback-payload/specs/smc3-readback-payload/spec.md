# Spec Delta

## Purpose

Define how the SMC3 readback diagnostic extracts the two payload bytes from validated five-byte responses and maps them to feedback and target fields using the SMC3 firmware reference implementation's documented scaling and byte ordering.

## ADDED Requirements

### Requirement: Map payload bytes to feedback and target using reference scaling

When the diagnostic receives a validated five-byte SMC3 readback response, it SHALL extract `response[2]` as `payload_byte_1_raw` (feedback byte) and `response[3]` as `payload_byte_2_raw` (target byte), assign `feedback_raw` from `payload_byte_1_raw` and `target_raw` from `payload_byte_2_raw` (raw byte values in the 0–255 range), and compute `feedback_decoded = feedback_raw × 4` and `target_decoded = target_raw × 4`.

#### Scenario: Standard feedback and target byte mapping

- **GIVEN** a five-byte response `[0x5B, 0x41, 0x7E, 0x80, 0x5D]` with valid framing (Motor A, standard mode)
- **WHEN** `_analyze_response()` processes the response with `reverse_motor1=False`
- **THEN** `payload_byte_1_raw` is `126` (0x7E), `payload_byte_2_raw` is `128` (0x80), `feedback_raw` is `126`, `target_raw` is `128`, `feedback_decoded` is `504` (126 × 4), and `target_decoded` is `512` (128 × 4)

### Requirement: Decoded values are quantized approximations

The diagnostic SHALL compute `feedback_decoded` and `target_decoded` as `raw_byte × 4`, yielding values in the 0–1020 range in increments of four. Because the firmware performs integer division by four before transmission, the lower two bits of the original ADC reading are discarded; the decoded values are quantized approximations that may not equal the original position.

#### Scenario: Decoded values are in 0–1020 range in increments of four

- **GIVEN** a five-byte response `[0x5B, 0x41, 0x01, 0x03, 0x5D]` with valid framing
- **WHEN** `_analyze_response()` processes the response
- **THEN** `feedback_decoded` is `4` (1 × 4) and `target_decoded` is `12` (3 × 4) — both in the 0–1020 range, in increments of four

#### Scenario: Decoded values are quantized approximations, not exact originals

- **GIVEN** a five-byte response `[0x5B, 0x41, 0x01, 0x01, 0x5D]` with valid framing (raw byte 1 = original ADC value 1–4, all truncated to 0 before transmission)
- **WHEN** `_analyze_response()` processes the response
- **THEN** `feedback_decoded` is `4` (1 × 4) — a quantized approximation; the original ADC value may have been 1, 2, 3, or 4

#### Scenario: Map payload bytes with standard scaling

- **GIVEN** a five-byte response `[0x5B, 0x41, 0x7E, 0x80, 0x5D]` with valid framing (Motor A, standard mode)
- **WHEN** `_analyze_response()` processes the response with `reverse_motor1=False`
- **THEN** `payload_byte_1_raw` is `126` (0x7E), `payload_byte_2_raw` is `128` (0x80), `feedback_raw` is `126`, `target_raw` is `128`, `feedback_decoded` is `504` (126 × 4), and `target_decoded` is `512` (128 × 4)

#### Scenario: Map payload bytes with zero values

- **GIVEN** a five-byte response `[0x5B, 0x41, 0x00, 0x00, 0x5D]` with valid framing
- **WHEN** `_analyze_response()` processes the response with `reverse_motor1=False`
- **THEN** `payload_byte_1_raw` is `0`, `payload_byte_2_raw` is `0`, `feedback_raw` is `0`, `target_raw` is `0`, `feedback_decoded` is `0`, and `target_decoded` is `0`

#### Scenario: Map payload bytes with maximum values

- **GIVEN** a five-byte response `[0x5B, 0x41, 0xFF, 0xFF, 0x5D]` with valid framing
- **WHEN** `_analyze_response()` processes the response with `reverse_motor1=False`
- **THEN** `payload_byte_1_raw` is `255` (0xFF), `payload_byte_2_raw` is `255` (0xFF), `feedback_raw` is `255`, `target_raw` is `255`, `feedback_decoded` is `1020` (255 × 4), and `target_decoded` is `1020` (255 × 4)

#### Scenario: Scale Motor 2 and Motor 3 responses

- **GIVEN** a five-byte response `[0x5B, 0x42, 0x64, 0xC8, 0x5D]` with valid framing (Motor B)
- **WHEN** `_analyze_response()` processes the response
- **THEN** `payload_byte_1_raw` is `100` (0x64), `payload_byte_2_raw` is `200` (0xC8), `feedback_raw` is `100`, `target_raw` is `200`, `feedback_decoded` is `400` (100 × 4), and `target_decoded` is `800` (200 × 4)

### Requirement: Motor inversion SHALL be deferred until hardware confirmation

The SMC3 firmware reference implements a `#define REVERSE_MOTOR1` option that inverts motor feedback/target values. The DOF Reality H3 also reverses one motor's direction, but **it is unknown which motor (Motor 1 or Motor 2) is reversed on the H3**. The diagnostic SHALL NOT apply any motor inversion logic until the reversed motor identity is confirmed by hardware testing. Until confirmed, `feedback_decoded` and `target_decoded` SHALL be computed as `raw_byte × 4` without inversion.

#### Scenario: Motor inversion is deferred pending hardware confirmation

- **GIVEN** the diagnostic receives a readback response for any motor
- **WHEN** the reversed motor identity is unknown
- **THEN** the diagnostic SHALL apply standard scaling only — no inversion — and `feedback_decoded` and `target_decoded` SHALL be computed as `raw_byte × 4` without inversion

#### Scenario: Standard scaling applied when inversion target is unknown

- **GIVEN** a five-byte response `[0x5B, 0x41, 0x80, 0x80, 0x5D]` with valid framing (Motor A)
- **WHEN** `_analyze_response()` processes the response and the reversed motor identity is unknown
- **THEN** `payload_byte_1_raw` is `128` (0x80), `payload_byte_2_raw` is `128` (0x80), `feedback_raw` is `128`, `target_raw` is `128`, `feedback_decoded` is `512` (128 × 4), and `target_decoded` is `512` (128 × 4) — no inversion applied

### Requirement: Set decode_status based on validation

The diagnostic SHALL set `decode_status` to `"OK"` when the response passes all framing, length, and motor-identifier validation checks. It SHALL set `decode_status` to `"ERROR"` when the response fails any validation check.

#### Scenario: decode_status is OK for valid response

- **GIVEN** a five-byte response `[0x5B, 0x41, 0x7E, 0x80, 0x5D]` with valid framing
- **WHEN** `_analyze_response()` processes the response
- **THEN** `decode_status` is written as `"OK"` to the decoded CSV

#### Scenario: decode_status is ERROR for invalid framing

- **GIVEN** a response `[0x41, 0x7E, 0x80]` (missing start/end bytes)
- **WHEN** `_analyze_response()` processes the response
- **THEN** `decode_status` is written as `"ERROR"` to the decoded CSV

#### Scenario: decode_status is ERROR for wrong motor identifier

- **GIVEN** a five-byte response `[0x5B, 0x42, 0x7E, 0x80, 0x5D]` (Motor B) when requesting Motor A
- **WHEN** `_analyze_response()` processes the response for Motor A
- **THEN** `decode_status` is written as `"ERROR"` to the decoded CSV

### Requirement: Only extract payload bytes from validated responses

Payload byte extraction and field mapping SHALL only occur when the response satisfies all framing validation checks: correct start byte (`0x5B`), correct end byte (`0x5D`), correct length (5 bytes), and matching motor identifier.

#### Scenario: Payload bytes not extracted from invalid framing

- **GIVEN** a response `[0x5B, 0x41, 0x7E, 0x80]` (4 bytes, missing end delimiter)
- **WHEN** `_analyze_response()` processes the response
- **THEN** `feedback_raw`, `target_raw`, `payload_byte_1_raw`, and `payload_byte_2_raw` are not populated from the incomplete data

#### Scenario: Payload bytes not extracted from wrong motor identifier

- **GIVEN** a five-byte response `[0x5B, 0x42, 0x7E, 0x80, 0x5D]` (Motor B) when requesting Motor A
- **WHEN** `_analyze_response()` processes the response for Motor A
- **THEN** `feedback_raw`, `target_raw`, `payload_byte_1_raw`, and `payload_byte_2_raw` are not populated

### Requirement: Preserve raw response in CSV

The diagnostic SHALL continue to write the complete original response bytes to the `raw_response` column in the decoded CSV.

#### Scenario: Raw response preserved

- **GIVEN** a five-byte response `[0x5B, 0x41, 0x7E, 0x80, 0x5D]`
- **WHEN** `_analyze_response()` processes the response
- **THEN** `raw_response` is written as `"5B 41 7E 80 5D"` to the decoded CSV

### Requirement: Preserve framing validation in CSV

The diagnostic SHALL continue to write the framing validation result to the `framing_valid` column in the decoded CSV.

#### Scenario: Framing valid response logged correctly

- **GIVEN** a properly framed five-byte response `[0x5B, 0x41, 0x7E, 0x80, 0x5D]`
- **WHEN** `_analyze_response()` processes the response
- **THEN** `framing_valid` is written as `"true"` to the decoded CSV

#### Scenario: Framing invalid response logged correctly

- **GIVEN** an improperly framed response `[0x41, 0x7E, 0x80]`
- **WHEN** `_analyze_response()` processes the response
- **THEN** `framing_valid` is written as `"false"` to the decoded CSV

### Requirement: CSV schema includes all field columns

The decoded CSV header SHALL include payload extraction and decoded position columns alongside existing columns.

#### Scenario: Decoded CSV header includes all columns

- **GIVEN** a `DiagnosticSession` writes decoded data
- **THEN** the decoded CSV header contains: `request_id, motor, raw_response, framing_valid, feedback_raw, target_raw, feedback_decoded, target_decoded, decode_status, payload_byte_1_raw, payload_byte_2_raw`

#### Scenario: Active test CSV header includes all columns

- **GIVEN** a `DiagnosticSession` writes active test data
- **THEN** the active test CSV header contains `feedback_raw`, `target_raw`, `feedback_decoded`, `target_decoded`, `decode_status`, `payload_byte_1_raw`, and `payload_byte_2_raw` columns in addition to existing columns
