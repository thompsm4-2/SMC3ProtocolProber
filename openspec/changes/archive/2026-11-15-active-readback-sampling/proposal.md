# Proposal

## Why

The current active target diagnostic sends a single readback sample immediately after the settling delay, which is insufficient to determine whether the platform's feedback and target values actually stabilize during the settling period. Without multiple samples, transient drift or oscillation between the commanded target and settled feedback cannot be detected.

## What Changes

- During each active-test target step, collect multiple readback samples throughout the configured settling period instead of a single sample.
- Record each sample with its timestamp, step number, motor, commanded target, feedback raw/decoded values, target raw/decoded values, and decode status.
- Preserve the existing command sequence, target limits, settling configuration, and motor-control behavior.
- Keep the existing command transmission and readback protocol unchanged.
- Make the sampling behavior deterministic and testable with fake serial responses.

## Capabilities

### New Capabilities

- `active-readback-sampling`: Collects multiple readback samples during the settling period of each active-test target step, recording timestamps, feedback, and target values for each sample.

## Impact

- **Modified files**: `src/calibration/smc3_readback_diagnostic.py` (active test sampling logic, CSV output)
- **Modified files**: `src/calibration/test_readback_diagnostic.py` (tests for multi-sample collection, timing, and readback failure handling)
- **New spec**: `openspec/specs/active-readback-sampling/spec.md`
- **CSV schema**: Active test CSV gains `sample_index` and `sample_timestamp` columns; each step produces multiple rows instead of one.
