# Spec Delta

## ADDED Requirements

### Requirement: Collect multiple readback samples per active-test step

When `ReadbackDiagnostic.run_active()` processes each target in the active-test sequence, it SHALL collect multiple readback samples during the settling period instead of a single sample. The number of samples per step SHALL be configurable via a `--active-samples` CLI argument with a default of 5. The samples SHALL be spaced evenly across the settling period.

#### Scenario: Default sample count is 5

- **GIVEN** `run_active()` is called with `settling_delay=0.5` and no `--active-samples` override
- **THEN** 5 readback samples are collected during each settling period

#### Scenario: Configurable sample count

- **GIVEN** `run_active()` is called with `--active-samples 10`
- **THEN** 10 readback samples are collected during each settling period

#### Scenario: Sample spacing distributes evenly across settling period

- **GIVEN** `run_active()` is called with `settling_delay=1.0` and `sample_count=4`
- **THEN** samples are collected at approximately 0.25s, 0.50s, 0.75s, and 1.00s after the target command is transmitted

#### Scenario: Single sample produces same timing as before

- **GIVEN** `run_active()` is called with `--active-samples 1` and `settling_delay=0.5`
- **THEN** a single sample is collected at approximately 0.5s after the target command is transmitted

### Requirement: Record sample metadata for each readback

Each readback sample SHALL be logged as a separate CSV row with `sample_index` (zero-based) and `sample_timestamp` (ISO 8601) columns.

The existing columns (`step`, `motor`, `target`, `feedback_raw`, `target_raw`, `feedback_decoded`, `target_decoded`, `decode_status`, `timestamp`, `transmitted_hex`, `payload_byte_1_raw`, `payload_byte_2_raw`) SHALL be preserved and repeated for each sample row.

#### Scenario: Sample index starts at zero

- **GIVEN** `run_active()` collects 3 samples for step 0
- **THEN** the `sample_index` values are 0, 1, and 2

#### Scenario: Sample timestamp records readback receive time

- **GIVEN** a readback response is received at a specific wall-clock time
- **THEN** `sample_timestamp` records that time in ISO 8601 format (e.g., `2026-11-13T10:30:00.123456`)

#### Scenario: Existing columns repeated for each sample

- **GIVEN** `run_active()` collects 4 samples for step 2 on motor B with target 520
- **THEN** the CSV contains 4 rows for step 2, each with `step=2`, `motor=B`, `target=520` and the same `transmitted_hex` value

### Requirement: Handle readback failures per sample

When a readback poll for a given sample index times out or returns an invalid response, the sample SHALL be logged with `decode_status="ERROR"` and `feedback_raw`, `target_raw`, `feedback_decoded`, and `target_decoded` set to `null`. The sampling loop SHALL continue collecting remaining samples for that step.

#### Scenario: Timeout produces ERROR sample

- **GIVEN** the second of 5 samples times out during readback
- **THEN** that sample is logged with `decode_status="ERROR"` and decoded fields set to `null`
- **THEN** sampling continues for the remaining 3 samples

#### Scenario: Invalid response produces ERROR sample

- **GIVEN** the third of 5 samples returns a malformed response that fails framing validation
- **THEN** that sample is logged with `decode_status="ERROR"` and decoded fields set to `null`
- **THEN** sampling continues for the remaining 2 samples

#### Scenario: All samples fail

- **GIVEN** all 5 samples for a step fail with timeouts
- **THEN** all 5 rows are logged with `decode_status="ERROR"` and null decoded fields
- **THEN** the step completes and the next target is processed

### Requirement: Preserve existing command sequence and limits

The active test SHALL continue to use the same `ACTIVE_TEST_SEQUENCE` targets, the same `smc3_frame()` encoding, the same motor iteration, and the same position clamping to `[MIN_POS, MAX_POS]`. No targets SHALL be added, removed, or reordered.

#### Scenario: Target sequence unchanged

- **GIVEN** `run_active()` is called with default parameters
- **THEN** the targets sent are `[512, 513, 514, 515, 516, 520, 524]` in that order

#### Scenario: Position clamping preserved

- **GIVEN** `run_active()` is called with a target below `MIN_POS`
- **THEN** the transmitted position is clamped to `MIN_POS` (0)

### Requirement: Preserve settling delay configuration

The settling delay SHALL remain configurable via the existing `--active-settle` CLI argument with the same default value. The total time per step SHALL increase proportionally to the number of samples.

#### Scenario: Default settling delay preserved

- **GIVEN** `run_active()` is called without `--active-settle`
- **THEN** the settling delay defaults to 0.5 seconds

#### Scenario: Custom settling delay respected

- **GIVEN** `run_active()` is called with `--active-settle 2.0`
- **THEN** the settling period is 2.0 seconds, and all samples are collected within that window
