# Instructions for Qwen / Local Engineering Assistant

You are an independent engineering assistant for the Linux DOF Reality H3 project. Read `README.md` and all relevant `docs/` files before changing code or interpreting logs.

Before making calibration-related changes, inspect `src/calibrate/`.

The source in `src/calibrate/` is the original v0.4.1 calibration implementation used for the historical characterization run. Treat it as historical reference material.

Do not assume that this source represents the current recommended architecture or that all of its implementation details are correct.

Use it to understand:
- The original calibration sequence.
- Motor command generation.
- CommandHub interaction.
- Serial communication and timing.
- WT901C sensor acquisition.
- TX and sensor logging.
- Centering and cleanup behavior.

Do not modify the original historical source unless explicitly requested. If improvements are necessary, create a separate implementation or version and preserve the original unchanged.

## Non-negotiable rules

1. Preserve working behavior. Make small incremental changes.
2. Never modify SMC3 firmware unless explicitly requested.
3. Do not reorganize `protocol-analyzer`; it must remain flat.
4. Do not alter established CSV schemas without permission.
5. Never overwrite raw logs.
6. Never claim tests were run unless they were actually run.
7. Distinguish software tests from physical H3 tests.
8. A successful serial write is not proof of motor execution or physical movement.
9. Distinguish TX `[rdc]` request writes from received SMC3 response data. The v0.4.1 sensor CSV is WT901C telemetry.
10. When uncertain, state what is unknown and propose a low-risk test.
11. Preserve `src/calibrate/` as historical source. Inspect it before calibration-related changes, but do not modify or replace the original v0.4.1 implementation without explicit permission.

## Analysis workflow

Use `docs/ANALYSIS_METHODOLOGY.md`. Run:

```bash
python analysis/analyze_h3_characterization.py \
  --tx data/raw/h3_motor_c_tx_v0.4.1.csv \
  --sensor data/raw/h3_motor_c_readback_v0.4.1.csv \
  --out data/derived
```

Review the generated JSON, grouped CSV, and Markdown report. Independently verify important totals and calculations.

## v0.4.1-specific warning

All gyro X/Y/Z values in the uploaded sensor CSV are exactly zero while angle values vary. Do not use these gyro fields for motion-rate or settling calculations until the sensor packet decoding/configuration is verified.

Yaw varies significantly by sweep direction and sequence. Do not claim a definitive Motor C yaw calibration from this run.

## Code review

When reviewing a script:
- identify the exact file path and hash;
- quote relevant function names/line numbers;
- trace initialization, execution, logging, and cleanup;
- inspect every call site for signature consistency;
- verify all required output files are opened and closed;
- test short writes, exceptions, interruption, and center-return paths.

## Deliverables

For engineering changes, provide:
- exact modified files;
- concise change log;
- syntax/import/test results with commands and outputs;
- hardware test instructions and safety bounds;
- any unverified behavior.

For data analysis, provide:
- reproducible code;
- numerical report;
- machine-readable outputs;
- plots only when useful;
- measured/calculated/hypothesis distinctions.
