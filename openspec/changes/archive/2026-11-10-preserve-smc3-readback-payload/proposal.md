# Proposal

## Why

The SMC3 readback diagnostic utility's `_analyze_response` method receives valid five-byte responses (e.g., `5B 41 7E 80 5D`) but unconditionally writes zeros into `feedback_raw` and `target_raw` columns in the decoded CSV. The two payload bytes that arrive after the motor identifier are discarded, losing data that is already mapped to concrete semantics by the SMC3 firmware reference implementation. The payload bytes must be extracted, mapped to feedback and target fields using the reference implementation's documented scaling, and preserved in the CSV.

## Protocol Reference

The byte mapping and scaling are derived from the open-source [SMC3 firmware reference implementation](https://github.com/SimulatorMotorController/SMC3/blob/master/SMC3.ino), an Arduino sketch designed for motion simulators with up to three motors. **This is not official DOF Reality documentation or verified firmware** — it is an accepted community reference whose readback protocol is used here as a working specification.

The firmware's `SendTwoValues` function sends readback responses in the format:

```
[START_BYTE][motor_id][byte_1][byte_2][END_BYTE]
```

For motor position readback commands (`rdA`, `rdB`, `rdC`), the firmware sends:

```c
// Standard mode
SendTwoValues('A', Feedback1/4, Target1/4, ComPort);
SendTwoValues('B', Feedback2/4, Target2/4, ComPort);
SendTwoValues('C', Feedback3/4, Target3/4, ComPort);

// With REVERSE_MOTOR1 flag (Motor 1 only)
SendTwoValues('A', (1023-Feedback1)/4, (1023-Target1)/4, ComPort);
```

### Scaling

- `FeedbackN` values come from `analogRead()` on pins A0/A1/A2 (10-bit, 0–1023 range)
- Both feedback and target are **integer-divided by 4** before transmission
- Resulting bytes fit in the 0–255 range (single byte each)
- To reconstruct: `raw_value = byte * 4` (loses lower 2 bits of precision)

## What Changes

- **Modify** `src/calibration/smc3_readback_diagnostic.py`:
  - In `_analyze_response()`, extract `response[2]` and `response[3]` as unsigned byte values when the response satisfies framing, length, and motor-identifier checks.
  - Assign `response[2]` to `payload_byte_1_raw` and `feedback_raw` (feedback byte, 0–255), and `response[3]` to `payload_byte_2_raw` and `target_raw` (target byte, 0–255).
  - Compute `feedback_decoded = feedback_raw × 4` and `target_decoded = target_raw × 4` (reconstructed position values, 0–1020 in increments of 4). The firmware's integer division by four discards the original lower two bits, so the decoded values are quantized approximations, not necessarily the exact original ADC readings.

  - Set `decode_status` to `"OK"` for valid responses and `"ERROR"` for responses that fail framing validation.
  - Keep `raw_response` containing the complete original response bytes.
  - Keep `framing_valid` representing framing validation as before.
- **Update CSV schema** for `decoded_readbacks_*.csv` and `active_test_*.csv`:
  - Add `feedback_decoded` and `target_decoded` columns for the reconstructed position values (0–1020 in increments of 4).
  - Keep existing columns (`raw_response`, `framing_valid`, `feedback_raw`, `target_raw`, `decode_status`) with their corrected semantics: `feedback_raw` and `target_raw` contain raw bytes (0–255); `feedback_decoded` and `target_decoded` contain the quantized reconstructed values (0–1020).
  - Retain `payload_byte_1_raw` and `payload_byte_2_raw` columns for the raw extracted bytes.

- **Add focused regression tests** in `src/calibration/test_readback_diagnostic.py` covering payload extraction, scaling, zero/255 edge values, invalid framing, wrong motor identifiers, and decode status values.
- **Preserve** all existing behavior: no changes to serial communication, polling, timing, motor commands, simulation behavior, or hardware interaction.

## Capabilities

### New Capabilities

- **smc3-readback-payload**: Extract the two payload bytes from validated SMC3 readback responses and map them to feedback and target fields using the SMC3 firmware reference implementation's documented scaling and byte ordering.

### Modified Capabilities

<!-- None — this change creates a new capability; no existing spec-level requirements change. -->

## Impact

- **Files modified**: `src/calibration/smc3_readback_diagnostic.py`, `src/calibration/test_readback_diagnostic.py`
- **CSV schema change**: `feedback_raw` and `target_raw` now populated with raw bytes (0–255); `decode_status` uses `"OK"`/`"ERROR"`; new `feedback_decoded` and `target_decoded` columns for reconstructed position values (0–1020 in increments of 4)
- **No breaking changes** to existing CSV consumers (no external consumers identified)
- **No changes** to serial communication, polling behavior, or motor commands
