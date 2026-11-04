# Linux DOF Reality H3 Engineering Project
## Portable Engineering Handoff — Version 1.0

**Purpose:** Provide a portable, implementation-independent reference for continuing the DOF Reality H3 Linux control and characterization project with ChatGPT, Qwen, or another engineering assistant.

**Project status:** Active development  
**Primary development platform:** Linux / CachyOS  
**Primary language:** Python  
**Long-term language goal:** Rust  
**Hardware:** DOF Reality H3, SMC3 Arduino controller, Witmotion WT901C

---

# 1. Project Mission

Develop an independent Linux-based control and motion-cue system for the DOF Reality H3 motion platform.

The project has several long-term objectives:

1. Understand the H3 mechanical and electrical behavior.
2. Develop reliable Linux communication with the SMC3 Arduino controller.
3. Characterize motor commands against actual platform movement.
4. Use the WT901C sensor to measure physical platform orientation and response.
5. Develop motion cues from X-Plane flight telemetry.
6. Eventually implement a general-purpose flight simulation motion-cueing system.
7. Port proven Python functionality to Rust when the architecture is sufficiently mature.

The project should be developed incrementally. Reliable measurements and reproducible results take priority over rapid implementation.

# 2. Engineering Principles

All participating engineering assistants must follow these principles.

## 2.1 Preserve working functionality

- Do not casually replace known-working transport code.
- Do not reorganize established project directories without permission.
- Do not change existing CSV schemas without permission.
- Do not modify SMC3 firmware unless explicitly requested.
- Prefer small, independently testable changes.

## 2.2 Verify code before hardware testing

Before asking the user to connect or power the H3:

- Check imports and syntax.
- Check function signatures and call sites.
- Check initialization and cleanup paths.
- Test command encoding.
- Use simulated serial devices or loopback tests where appropriate.
- Test logging and file creation.
- Test exception handling.
- Test interruption and centering behavior.

The user should not have to power the motion platform to discover ordinary programming errors.

## 2.3 Evidence discipline

Every technical conclusion must be identified as one of:

- **Measured:** Directly observed in recorded hardware or sensor data.
- **Calculated:** Mathematically derived from measured data.
- **Source-inspected:** Established by examining source code or documentation.
- **Software-tested:** Demonstrated without physical hardware.
- **Physically tested:** Confirmed on the actual H3.
- **Hypothesis:** A possible explanation that requires further testing.

Never present a hypothesis as a measured fact.

A successful serial write does not prove that the Arduino executed the command or that the platform moved.

# 3. Hardware Reference

## 3.1 DOF Reality H3

The platform uses three motors:

| Motor | Project designation | General function |
|---|---|---|
| A | Motor A | Pitch/roll mechanism |
| B | Motor B | Pitch/roll mechanism |
| C | Motor C | Additional motion axis, associated with yaw effects |

Important mechanical observation:

- Motors A and B are mechanically coupled in the H3 pitch/roll arrangement.
- Motor C produces a different set of physical effects.
- Cross-axis movement must be measured rather than assumed absent.

The H3 should be treated as a coupled mechanical system until characterization establishes its actual response.

## 3.2 SMC3 controller

Known hardware information:

- Arduino-based SMC3 controller.
- SMC3 firmware version observed: 23.07.
- Windows SMC3 Utility identified the controller as `SH3_M3_b-D1`.
- Previous Windows serial port: COM4.
- Linux H3 serial device observed: `/dev/ttyACM0`.
- Serial baud rate: 500000.
- Nominal motor center: 512.
- Position range: 0–1023.
- Motors: A, B, C.

Confirm device names before every hardware session. Linux device numbering can change.

## 3.3 SMC3 command format

Motor commands use five bytes:

`[`, motor identifier, high byte, low byte, `]`

Example Python encoder:

```python
def smc3_frame(motor, position):
    position = max(0, min(1023, int(position)))
    return bytes((
        91,
        ord(motor),
        (position >> 8) & 255,
        position & 255,
        93
    ))
```

Examples:

| Command | Bytes |
|---|---|
| Motor A = 512 | `5B 41 02 00 5D` |
| Motor A = 510 | `5B 41 01 FE 5D` |
| Enable | `5B 65 6E 61 5D` |
| Version request | `5B 76 65 72 5D` |

Additional readback requests:

- `[rda]`
- `[rdb]`
- `[rdc]`

The exact response format and interpretation of these readback commands must be established from captured data. Do not assume their meaning.

## 3.4 Witmotion WT901C

Sensor:

- Model: WT901C RS232.
- USB serial adapter: CH341.
- Linux device observed: `/dev/ttyUSB0`.
- Baud rate: 9600.
- Sensor is mounted on the H3.
- SRS has previously used this sensor for motion compensation.

Known WIT packet structure:

- 11-byte packets.
- Synchronization byte: `0x55`.
- Packet types:
  - `0x51`: acceleration.
  - `0x52`: angular velocity.
  - `0x53`: angle.
  - `0x54`: magnetometer.
- Checksum: sum of first 10 bytes modulo 256.
- Values use signed little-endian representation.

Known conversion scales:

| Measurement | Conversion |
|---|---|
| Acceleration | 1/2048 g |
| Angular velocity | 1/16.384 degrees/second |
| Angle | 180/32768 degrees |
| Magnetometer | Raw values |

Sensor measurements must be interpreted with awareness of orientation, mounting alignment, calibration, and magnetic interference.

# 4. Software Architecture

## 4.1 Known-working CommandHub baseline

Version: `v0.3.5.1`

This is the user-reported physically working H3 transport implementation.

Important design properties:

- CommandHub owns all serial writes.
- Single worker performs serial transmission.
- Default command rate: 30 Hz.
- Hybrid queue behavior:
  - FIFO behavior across motor slots.
  - Latest-value-wins for each motor.
  - `_latest_by_motor` storage.
  - Queue size of one.
- Uses `read_with_timeout`.
- Reset and pose commands pass through CommandHub.

This architecture should be preserved as a known-working reference.

## 4.2 Characterization software

The characterization program intentionally sends individual sweep commands rather than relying on the CommandHub latest-value-wins behavior.

This is important because a characterization sweep must transmit each intended measurement point.

Requirements:

- Explicit motor selection.
- Configurable position range.
- Configurable step size.
- Configurable settling time.
- Configurable measurement duration.
- Accurate command logging.
- Accurate sensor logging.
- Safe return-to-center behavior.
- Unique output filenames.
- Clear reporting of incomplete or interrupted runs.

Only one program should own H3 serial communication at a time.

The WT901C uses a separate serial connection.

## 4.3 Directory constraints

The existing `protocol-analyzer` directory must remain flat.

Do not reorganize it into a `src` structure without explicit permission.

# 5. Characterization History

## 5.1 Early motor movement experiments

Observed behavior:

- Step sizes of 1–2 produced barely perceptible movement.
- Step sizes of 4–5 were more noticeable.
- Step sizes around 10 produced more obvious movement.

These are observations, not proof of a motor dead zone.

Earlier timing experiments:

| Test | Observed time |
|---|---:|
| 512 to 612, step 1 | 10.45 s |
| 512 to 612, step 5 | 2.35 s |
| 512 to 612, step 10 | 1.30 s |

A no-wait test requested 100 position changes but transmitted only five frames over 0.1377 seconds. This demonstrated command coalescing, not actual motor speed.

## 5.2 Previous WT901C characterization

An earlier sensor capture contained:

- 804 rows.
- 200 center samples.
- 202 Motor A samples.
- 202 Motor B samples.
- 200 Motor C samples.

Previously calculated slopes:

| Motor | Roll slope | Pitch slope | Yaw slope |
|---|---:|---:|---:|
| A | -0.006994°/count | -0.010613°/count | +0.002686°/count |
| B | +0.007596°/count | -0.011775°/count | Approximately flat |
| C | Approximately flat | Approximately flat | +0.005544°/count |

These are historical preliminary results, not final calibrated motor models.

Earlier observations included:

- A/B return hysteresis around 0.3–0.5 degrees.
- C yaw response was rougher and potentially path-dependent.
- C return-center yaw differed by approximately 0.94 degrees in one test.
- Magnetometer readings varied between return conditions.

Yaw measurements must be treated cautiously because magnetic interference and AHRS behavior may influence the reported heading.

The WT901C reader previously sampled the latest acceleration, gyro, and magnetometer values when processing angle packets. These values were not necessarily perfectly time-synchronized.

# 6. Current Characterization Software Status

## 6.1 Qwen v0.4

User physically tested this version.

Observed results:

- Connected to the H3.
- Motor C initially moved.
- Characterization crashed a few movements into the run.
- Requested `--tx-log` file was not created.
- The characterization did not complete.

Status: **Failed physical test.**

Do not treat initial motor movement as evidence that the entire implementation worked.

## 6.2 ChatGPT v0.4.1

User reports that this version completed its characterization run successfully.

The user has both resulting logs.

Status:

- Physical characterization run completed.
- TX log available.
- Sensor/readback log available.
- Detailed analysis pending upload and examination.

This is the current successful characterization reference.

Do not claim that v0.4.1 has been physically validated beyond the run reported by the user. The logs must be examined to establish exactly what happened.

# 7. Standard Log Analysis Methodology

The purpose of characterization is to determine how commanded motor positions relate to actual measured platform movement.

**Commanded motor position is not equivalent to measured platform orientation.**

Analysis must use both logs.

## 7.1 Stage 1 — Data integrity

Check:

- File existence and size.
- Number of records.
- Header and column names.
- Timestamp validity.
- Duplicate timestamps.
- Missing or malformed records.
- Sampling intervals.
- Timing gaps.
- Unexpected motor identifiers.
- Unexpected positions.
- Whether the run appears complete.

Report all assumptions.

## 7.2 Stage 2 — TX command analysis

Reconstruct the actual command sequence.

Calculate:

- Commands per motor.
- First and last command times.
- Command intervals.
- Position progression.
- Reversals.
- Duplicate commands.
- Missing expected positions.
- Time spent at each commanded position.
- Whether a return-to-center command was transmitted.

Preserve the distinction between a command being transmitted and a physical movement being completed.

## 7.3 Stage 3 — Sensor analysis

Analyze measured:

- Roll.
- Pitch.
- Yaw.
- Acceleration.
- Angular velocity.
- Magnetometer values, when available.

For each commanded motor position, calculate:

- Mean sensor reading.
- Standard deviation.
- Minimum and maximum.
- Measurement count.
- Stability over the measurement interval.

Identify sensor jumps, outliers, and suspicious measurements.

## 7.4 Stage 4 — Correlation

Align TX commands and sensor readings using timestamps.

Account for:

- Command transmission time.
- Motor response delay.
- Settling time.
- Sensor sampling intervals.
- Possible sensor filtering delay.

Do not assume the sensor reading immediately after a command represents the final physical response.

## 7.5 Stage 5 — Mechanical characterization

Calculate where the data supports it:

- Degrees of roll per motor count.
- Degrees of pitch per motor count.
- Degrees of yaw per motor count.
- Linear regression slopes.
- R-squared values.
- Nonlinear response.
- Cross-axis coupling.
- Reversal hysteresis.
- Return-to-center repeatability.
- Settling time.
- Response delay.
- Direction-dependent behavior.

Do not force a linear model if the data demonstrates nonlinear behavior.

## 7.6 Required report format

Every characterization report should contain:

1. Run identification and input files.
2. Data integrity summary.
3. TX command summary.
4. Sensor sampling summary.
5. Motor response results.
6. Axis coupling results.
7. Linearity and regression results.
8. Reversal and hysteresis results.
9. Return-to-center results.
10. Anomalies and limitations.
11. Conclusions.
12. Recommended next experiment.

Include numerical results and explain how they were calculated.

# 8. Qwen / Local LLM Engineering Instructions

Qwen is an independent engineering assistant, not merely a code generator.

It must:

- Read this handoff before modifying project code.
- Preserve existing working implementations.
- Clearly identify which source version it is analyzing.
- Never assume two files with the same version label are identical.
- Never claim a test was run unless it actually was.
- Never claim physical movement based solely on serial writes.
- Never invent missing log fields or measurement values.
- Explain formulas and assumptions.
- Produce reproducible Python analysis code.
- Validate its own calculations.
- Preserve raw source logs.
- Never overwrite original test data.

When analyzing a new characterization run, Qwen should produce:

- A human-readable Markdown report.
- A machine-readable results file.
- Reproducible analysis code.
- Any useful plots.
- A list of unresolved questions.

The same methodology should be usable by ChatGPT and Qwen.

# 9. Safety and Hardware Testing

The H3 is a powered moving platform.

Before physical tests:

- Confirm the platform is clear of obstructions.
- Use conservative position ranges.
- Confirm motor selection.
- Confirm center position.
- Ensure emergency power interruption is available.
- Run only one H3-control application at a time.

On interruption, attempt a safe return to center when communication and hardware conditions permit. Do not assume that centering is guaranteed after a crash or communication failure.

Do not run competing serial readers or writers against the same H3 connection.

# 10. Future Workstreams

## Workstream A — H3 characterization

Current priority.

- Complete analysis of v0.4.1 logs.
- Validate TX sequence.
- Establish actual sensor response.
- Improve repeatability.
- Characterize Motor A, B, and C independently.
- Determine mechanical coupling and hysteresis.

## Workstream B — WT901C sensor integration

- Validate packet decoding.
- Establish sensor orientation.
- Measure noise and drift.
- Examine magnetometer interference.
- Establish reliable timestamp alignment.
- Evaluate sensor calibration.

## Workstream C — X-Plane telemetry

- Capture X-Plane UDP data.
- Understand SRS telemetry flow.
- Develop a custom telemetry input layer.
- Implement flight-state and motion-cue inputs.

Known Windows environment:

- X-Plane receive port: 49010.
- Legacy receive port: 49000.
- Legacy send port: 49001.
- SRS previously configured for localhost port 49000.

## Workstream D — Motion cueing

Research and eventually implement:

- Pitch and roll cues.
- Coordinated and uncoordinated turns.
- Yaw cues.
- Stall cues.
- Acceleration and deceleration.
- Braking.
- Throttle and engine vibration.
- Ground movement.
- Vestibular limitations and motion perception.

The final system should be designed for a small three-axis simulation platform rather than simply copying the algorithms of large commercial simulators.

## Workstream E — Rust implementation

Only after Python behavior is understood and validated.

Preserve the same protocol, test cases, and measured behavior during the port.

# 11. Project Evidence and Version Control

Every important implementation should retain:

- Exact source file.
- Version identifier.
- Date.
- Changelog.
- Software test results.
- Physical test results, if applicable.
- Associated raw logs.
- Analysis report.
- SHA-256 hashes where practical.

Never silently replace a known-working version.

Maintain separate labels for:

- Known-working baseline.
- Experimental implementation.
- Software-tested implementation.
- Physically tested implementation.

# 12. Immediate Next Steps

1. Upload the successful v0.4.1 TX log.
2. Upload the associated sensor/readback log.
3. Validate both files and their timestamps.
4. Reconstruct the command sequence.
5. Correlate commanded positions with sensor measurements.
6. Produce the first authoritative v0.4.1 characterization report.
7. Convert the analysis procedure into reusable Python tools.
8. Give Qwen the same methodology and test data.
9. Compare ChatGPT and Qwen results against the same numerical reference.

**The immediate objective is not to write more motor-control code. It is to establish a reliable, repeatable understanding of what the H3 physically does when commanded.**
