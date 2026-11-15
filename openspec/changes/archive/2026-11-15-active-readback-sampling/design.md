# Design

## Context

The active target diagnostic in `smc3_readback_diagnostic.py` currently collects a single readback sample per target step after the settling delay. The `run_active()` method (lines 681-784) sends a position command, sleeps for `settling_delay`, calls `poll_motor()` once, decodes the response, and logs one CSV row per target. This single-sample approach cannot reveal whether the platform's position stabilizes during the settling window or whether it drifts/oscillates.

## Goals / Non-Goals

**Goals:**
- Collect multiple readback samples during each settling period
- Record each sample with timestamp, sample index, and all existing diagnostic fields
- Make the sampling configurable via a new `--active-samples` CLI argument (default 5)
- Ensure the sampling loop is deterministic and testable with `FakeSerial`
- Preserve all existing behavior: command sequence, target limits, protocol, and motor control

**Non-Goals:**
- Changing the SMC3 readback protocol or frame format
- Modifying passive readback polling behavior
- Adding new analysis or visualization of the collected samples
- Changing the settling delay calculation or default
- Fixing pre-existing bugs (e.g., the `KeyError` for `--motor ALL`)

## Decisions

### Decision 1: Evenly-spaced sampling within the settling period

Samples SHALL be collected at evenly-spaced intervals across the settling delay. For `N` samples over `settling_delay`, the interval between samples is `settling_delay / N`. The first sample is taken at `settling_delay / N`, and the last at `settling_delay`.

**Rationale**: This provides uniform coverage of the settling window, making it easy to identify when stabilization occurs. An alternative of fixed-interval sampling (e.g., every 50ms) would not adapt to different settling delays.

**Implementation**: Use a simple loop:
```python
sample_interval = settling_delay / sample_count
for i in range(sample_count):
    time.sleep(sample_interval)
    sample = poll_motor(DEFAULT_TIMEOUT, 0.05)
    log_sample(...)
```

### Decision 2: New CLI argument `--active-samples`

The sampling count SHALL be controlled by a new `--active-samples` argument on the CLI, defaulting to 5. This keeps the behavior backward-compatible (existing scripts continue to work with the same single-sample semantics only if they explicitly set `--active-samples 1`).

**Rationale**: A separate argument avoids changing the default behavior unexpectedly. The existing `--active-settle` argument continues to control the settling window independently.

### Decision 3: Separate `sample_index` and `sample_timestamp` columns

Each CSV row SHALL include `sample_index` (zero-based) and `sample_timestamp` (ISO 8601). The existing `timestamp` column (which currently records the readback time) SHALL be retained for backward compatibility, and `sample_timestamp` SHALL use the same value.

**Rationale**: `sample_index` enables programmatic identification of which sample in the sequence a row represents. `sample_timestamp` provides a standard, sortable timestamp format. Keeping the existing `timestamp` column avoids breaking downstream CSV consumers.

### Decision 4: Error samples logged as rows, not skipped

When a readback poll fails (timeout or invalid response), a row SHALL still be written with `decode_status="ERROR"` and null decoded fields. The sampling loop continues.

**Rationale**: This preserves the temporal structure of the settling window. A missing row would make it impossible to determine whether a gap was due to a failure or a different issue. Null values clearly indicate a failed sample.

### Decision 5: Use existing `poll_motor()` method

The multi-sample loop SHALL reuse the existing `poll_motor(DEFAULT_TIMEOUT, 0.05)` method for each sample. No new polling logic is introduced.

**Rationale**: `poll_motor()` already handles the read command framing, response reception, timeout, and the call to `_analyze_response()`. Reusing it avoids duplicating protocol logic and keeps the change focused on the sampling loop.

## Risks / Trade-offs

| Risk | Mitigation |
|------|-----------|
| Test runs take N× longer (N = sample count) with real hardware | Document the increased runtime; allow users to set `--active-samples 1` for quick checks |
| CSV file size grows N× per step | Acceptable trade-off for diagnostic value; document expected file sizes |
| FakeSerial response consumption must match sample count | Tests must provide `sample_count × target_count` canned responses; update existing simulation tests accordingly |
| New CSV columns may break downstream consumers | Add `sample_index` and `sample_timestamp` as new columns (not replacing existing ones); document the new columns |

## Migration Plan

No migration is needed. This is a backward-compatible change:
- Existing scripts continue to work; they simply get the new default of 5 samples per step instead of 1
- CSV output gains new columns but retains all existing columns
- No changes to the SMC3 protocol or command sequence
- Existing tests continue to pass after being updated to provide the correct number of canned responses for multi-sample runs

## Open Questions

None. All design decisions are resolved based on the spec requirements and existing codebase patterns.
