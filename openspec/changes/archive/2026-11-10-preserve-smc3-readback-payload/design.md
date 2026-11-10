# Design

## Context

The `_analyze_response()` method in `src/calibration/smc3_readback_diagnostic.py` (lines 557-588) receives valid five-byte SMC3 readback responses of the form `[motor_byte payload_byte_1 payload_byte_2]` (hex: `5B XX YY 5D`), but unconditionally writes zeros to `feedback_raw` and `target_raw` at line 579. The two payload bytes at indices 2 and 3 are discarded. No external CSV consumers have been identified; the decoded CSV is only written by the diagnostic itself.

The byte mapping and scaling are derived from the [SMC3 firmware reference implementation](https://github.com/SimulatorMotorController/SMC3/blob/master/SMC3.ino) — an open-source Arduino sketch for motion simulators. **This is not official DOF Reality documentation or verified firmware.**

## Goals / Non-Goals

**Goals:**
- Extract `response[2]` and `response[3]` as unsigned byte values in columns `payload_byte_1_raw` (feedback) and `payload_byte_2_raw` (target).
- Assign `feedback_raw` and `target_raw` to the raw byte values (0–255 range).
- Compute `feedback_decoded` and `target_decoded` using the reference implementation's `/4` scaling: `decoded_value = raw_byte * 4` (0–1020 range, in increments of four).
- Set `decode_status` to `"OK"` for valid responses and `"ERROR"` for invalid ones.
- Add focused regression tests covering payload extraction, scaling, edge values, invalid framing, and wrong motor identifiers.
- Maintain backward compatibility with existing CSV consumers (none identified, but schema change is additive).

**Non-Goals:**
- No changes to serial communication, polling, timing, or motor commands.
- No changes to simulation behavior or hardware interaction.
- No active motor tests.
- No modifications to historical source files, raw captures, or documentation.

## Decisions

### Decision 1: Map payload bytes using reference implementation scaling

**Choice:** Extract `response[2]` as `payload_byte_1_raw` (feedback) and `response[3]` as `payload_byte_2_raw` (target). Assign `feedback_raw` and `target_raw` to the raw byte values (0–255 range). Compute `feedback_decoded = feedback_raw * 4` and `target_decoded = target_raw * 4` (0–1020 range, in increments of four).

**Rationale:** The SMC3 firmware source code explicitly divides feedback and target values by 4 before sending them as single bytes. Reversing this operation (multiply by 4) restores a quantized position in the 0–1020 range. Because the firmware's integer division discards the lower two bits of the original ADC reading, the decoded values are quantized approximations — not necessarily the exact original position. The raw fields preserve the actual byte values received on the wire.

**Alternatives considered:**
- Leave bytes uninterpreted: rejected — the firmware reference provides a concrete, documented mapping.
- Treat bytes as a 16-bit value: rejected — the firmware sends two independent 8-bit values, not a single 16-bit value.

### Decision 2: Use "OK" / "ERROR" for decode_status

**Choice:** Set `decode_status` to `"OK"` when the response passes all validation checks, and `"ERROR"` when it fails any check.

**Rationale:** The firmware does not have an explicit decode status concept. Using "OK"/"ERROR" provides a clear binary signal: the response was successfully parsed and mapped, or it was rejected due to framing/validation failure. This is more informative than the previous `"UNKNOWN"` status.

**Alternatives considered:**
- Keep `"UNKNOWN"`: rejected — loses the information that the response was successfully decoded.
- Use more granular statuses (e.g., `"FRAMING_ERROR"`, `"MISMATCH_ERROR"`): rejected — the existing `framing_valid` column already captures framing failures; additional granularity adds complexity without clear benefit.

### Decision 3: Add new CSV columns rather than repurpose existing ones

**Choice:** Add `payload_byte_1_raw` and `payload_byte_2_raw` columns. Populate `feedback_raw` and `target_raw` with raw byte values (0–255). Add `feedback_decoded` and `target_decoded` for the reconstructed 0–1020 position values.

**Rationale:** Adding new columns preserves data without semantic commitment and avoids breaking any existing CSV readers. The `payload_byte_1_raw` and `payload_byte_2_raw` columns preserve the actual wire data independently of the semantic field mapping. The `feedback_raw` and `target_raw` columns now contain meaningful raw byte values instead of zeros. The decoded columns provide the reconstructed position values for downstream use.

**Alternatives considered:**
- Overwrite `feedback_raw`/`target_raw` with raw bytes only: rejected — the scaled 0–1020 values are more useful and match the firmware's native range.
- Add a single `payload_raw` field combining both bytes: rejected — loses individual byte granularity.

### Decision 4: Extract payload bytes only from fully validated responses

**Choice:** Only extract and map payload bytes when the response satisfies framing, length, and motor-identifier checks.

**Rationale:** Writing payload bytes from invalid responses would corrupt the CSV with garbage data. The existing framing validation already checks start byte (0x5B), end byte (0x5D), length, and motor byte (0x41/0x42/0x43).

**Alternatives considered:**
- Extract payload bytes regardless of validation: rejected — would produce misleading data.

## Risks / Trade-offs

| Risk | Mitigation |
|------|-----------|
| CSV schema change breaks existing consumers | No external consumers identified; column addition is backward-compatible (new columns at end, existing columns unchanged) |
| Payload bytes from invalid responses corrupt data | Payload extraction gated behind existing validation checks |
| Test coverage gap for edge cases | Focused tests for zero (0x00), max (0xFF), invalid framing, and wrong motor ID |
| Active test CSV also needs schema update | Update both `log_decoded()` and `log_active_test()` header writers |
| Reference implementation is not official DOF Reality firmware | Clearly documented as a community reference, not official documentation; scaling behavior validated against firmware source |

## Migration Plan

This change is additive and non-breaking:
1. New CSV columns are appended to existing headers.
2. `feedback_raw` and `target_raw` are now populated with meaningful raw byte values instead of zeros.
3. `decode_status` changes from `"UNKNOWN"` to `"OK"`/`"ERROR"` — consumers that check for non-empty status will see improvement; consumers that check for exact `"UNKNOWN"` value should be updated.
4. Existing tests continue to pass; new tests verify payload extraction and scaling.

## Open Questions

- **Which motor is reversed on the H3?** The SMC3 firmware's `REVERSE_MOTOR1` flag inverts Motor 1. The H3 also reverses a motor's direction, but it is unknown whether this corresponds to Motor 1 or Motor 2. Until confirmed, no inversion logic is implemented.
