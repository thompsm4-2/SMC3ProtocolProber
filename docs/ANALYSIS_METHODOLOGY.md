# Characterization Analysis Methodology

## Purpose

Determine the relationship between commanded motor position and measured platform motion. The command position is not the same as measured orientation.

## Inputs

1. TX CSV: command type, motor, position, bytes, write count, status, error, timestamp.
2. WT901C sensor CSV: timestamp, elapsed time, phase, motor, sweep direction, offset, A/B/C positions, sample index, roll/pitch/yaw, acceleration, gyro, magnetometer.

Do not confuse WT901C sensor rows with SMC3 controller response bytes.

## Stage 1 — Validate files

- Confirm headers and required columns.
- Count records and malformed rows.
- Check timestamp and elapsed-time monotonicity.
- Check duplicate sample indices and timestamps.
- Calculate sampling intervals and gaps.
- Identify missing/NaN fields.
- Check expected motor and position ranges.
- Determine whether the run completed and returned to center.

## Stage 2 — Reconstruct TX sequence

- Count commands by type and motor.
- Verify `bytes_written == expected`.
- Report non-OK statuses and errors.
- Decode/verify motor position sequence from `position` and `bytes_hex`.
- Preserve exact order and timing.
- Identify read requests separately from received responses.
- A successful write means bytes were accepted by the serial API; it does not prove controller execution.

## Stage 3 — Summarize sensor samples

Group by `(phase, sweep_direction, offset)` or by actual commanded A/B/C values. For each group calculate:
- sample count;
- start/end elapsed time;
- mean, standard deviation, minimum, maximum for each angle;
- mean acceleration, gyro, and magnetometer where useful.

Keep within-group sampling cadence separate from between-position pauses.

## Stage 4 — Correlate

Use timestamps and explicit phase/position metadata. If timestamp clocks differ, estimate and document the offset; do not silently align by row number.

Allow for:
- actuator movement delay;
- settling interval;
- sensor sample cadence;
- sensor filtering/update delay.

Do not interpret the first sample after a command as necessarily settled.

## Stage 5 — Mechanical response

Only when supported by data:
- fit angle versus motor count;
- report slope, intercept, R², number of distinct positions, and fit residuals;
- compare outbound and return readings at matching positions;
- quantify hysteresis;
- examine cross-axis coupling;
- compare initial and final center;
- estimate settling only when time-resolved data actually captures the transient.

Do not force a linear model if the response is nonlinear or path-dependent. Do not treat yaw as a reliable mechanical axis until sensor orientation, gyro output, magnetometer influence, and AHRS behavior are understood.

## Stage 6 — Reporting

Every report must separate:
- Measured facts.
- Calculated results.
- Source-inspected facts.
- Hypotheses.
- Limitations and unresolved questions.

Include input filenames and SHA-256 hashes, script version, exact calculations, and reproducible outputs.
