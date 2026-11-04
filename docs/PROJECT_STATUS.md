# Project Status

## Mission

Develop an independent Linux control and motion-cue system for the DOF Reality H3. Python is the prototype language; Rust is a later porting goal. The project combines SMC3 motor control, WT901C physical measurements, and eventually X-Plane telemetry and motion cueing.

## Current priority

The immediate priority is **measuring what the H3 physically does**, not adding more control features.

The v0.4.1 Motor C characterization run completed according to the user, and both associated CSV logs were uploaded. The archive's two files are preserved unchanged in `data/raw/`.

## Current v0.4.1 dataset facts

- TX log: 191 records.
- TX records by type: 69 `POSITION`, 120 `READ`, 1 `ENABLE`, 1 `VERSION`.
- Every TX row reports `status=OK`, `bytes_written=5`, `expected=5`.
- Position commands: 23 each for A, B, and C.
- A and B were held at 512.
- C position sequence: 512, 512, 492, 472, 452, 432, 412, 432, 452, 472, 492, 512, 532, 552, 572, 592, 612, 592, 572, 552, 532, 512, 512.
- The 120 read requests are `[rdc]` commands addressed to C.
- Sensor log: 622 records; 199 `center_reference` rows and 423 `sweep` rows.
- Sensor rows cover sample indices 131 through 1352.
- Sensor time span: approximately 122.126 seconds (from elapsed 15.058 to 137.184 seconds).
- The sensor sampling cadence within measurement blocks is approximately 100 ms. There are approximately 3.1-second pauses between blocks, consistent with the measurement sequence.
- All logged gyro X/Y/Z values are exactly zero. This is a data-quality question to investigate before using gyro values for response/settling analysis.
- The sensor's reported yaw changes across the sweep, but yaw interpretation is not yet validated against gyro or an independent reference.

## Preliminary interpretation

This is a successful *recorded characterization run* in the sense that the TX log contains a complete, successful-looking command sequence and the sensor file contains the sweep data. It does not prove that every write was executed mechanically; physical sensor data supports movement observations, subject to sensor validity.

The measured angle changes are small and direction/time dependent. The yaw series in particular is strongly path/time dependent. Do not publish a single definitive degrees-per-count calibration from this one run.

## Immediate next steps

1. Validate WT901C packet decoding and why gyro fields are zero.
2. Confirm sensor mounting axes and angle conventions.
3. Review grouped angle means and matched outbound/return points.
4. Repeat Motor C characterization after resolving sensor questions.
5. Only then derive a stable motor response model.
