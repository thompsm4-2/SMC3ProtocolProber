# Software Architecture and Constraints

## Known-working CommandHub baseline

Version `v0.3.5.1` is user-reported as physically working.

Its key design:
- CommandHub owns all SMC3 serial writes.
- One worker owns transmission.
- Default rate: 30 Hz.
- Hybrid queue: FIFO across motor slots, latest-value-wins per motor using `_latest_by_motor`; queue size one.
- Uses `read_with_timeout`.
- Reset and pose commands pass through the hub.

Do not casually refactor or replace this baseline.

## Original calibration source

Location:

`src/calibrate/`

This directory preserves the original v0.4.1 calibration source used to produce the historical Motor C characterization logs.

The source is retained for:
- Historical implementation reference.
- Understanding the original calibration sequence.
- Reviewing motor command generation and transmission.
- Understanding the relationship between motor commands and WT901C measurements.
- Comparing the original implementation against subsequent CommandHub-based development.

### Relationship to CommandHub

The original calibration script should be inspected to establish exactly how it interacts with the CommandHub and serial transport.

The established CommandHub baseline is v0.3.5.1, which owns SMC3 serial writes through a single worker.

Do not assume that the historical calibration script follows every constraint of the current architecture. Verify its actual command path before using it as a model for new development.

New characterization tools should preserve the established single-owner serial-write architecture unless a deliberate and documented alternative is introduced.

### Relationship to characterization tools

The original calibration source is separate from the repeatable analysis utility:

`analysis/analyze_h3_characterization.py`

The calibration source generates experimental commands and records hardware/sensor data.

The analysis utility processes the resulting CSV files after acquisition.

These are separate responsibilities:

1. Calibration source: performs the physical experiment.
2. CommandHub: manages SMC3 command transmission where used by the implementation.
3. WT901C acquisition: records platform orientation measurements.
4. Characterization analysis: evaluates the recorded data.
5. Reports: document measured results and conclusions.

The original v0.4.1 source is historical evidence and must remain unchanged.

## Characterization program

Characterization deliberately sends each sweep point explicitly. A latest-value-wins queue can coalesce intermediate points and is therefore not appropriate unless the test is specifically measuring queue behavior.

Requirements:
- One owner for H3 serial reads/writes.
- Separate WT901C serial reader is acceptable because it is a different port.
- Explicit motor, range, step, settling, and measurement duration.
- TX log records exact bytes, expected/written lengths, status, and errors.
- Sensor log records raw/decoded values and useful timing/phase metadata.
- Safe return-to-center attempt on normal completion and interruption.
- Unique output names; never overwrite prior evidence.

## Repository constraints

- `protocol-analyzer` must remain flat; do not move it into `src/`.
- Do not change existing CSV schemas without permission.
- No SMC3 firmware changes unless explicitly requested.
- Scripts should use `q` to quit where applicable.
- Keep changes incremental and preserve known-good versions.

## Testing before hardware

At minimum:
- Syntax/compile check.
- Import check.
- Command-frame unit tests.
- Fake-serial tests for full writes, short writes, exceptions, and timeout behavior.
- TX logger creation and row validation.
- Sensor parser tests using known packet examples.
- Normal completion and exception cleanup tests.
- Confirm centering path call signatures.
- Confirm no competing serial readers/writers.

Never claim a physical test based on software-only tests.
