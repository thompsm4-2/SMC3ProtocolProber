# Testing and Calibration History

## Early movement observations

Previous step-size experiments:
- Steps 1–2: barely perceptible.
- Steps 4–5: more noticeable.
- Step 10: more obvious.

These observations do not prove a motor dead zone.

Earlier 512→612 timing observations with settle=0:
- Step 1: 10.45 s.
- Step 5: 2.35 s.
- Step 10: 1.30 s.

A no-wait experiment requested 100 changes but transmitted only five frames over 0.1377 s. This demonstrated command coalescing, not motor speed.

## Earlier preliminary WT901C results

An earlier dataset contained 804 rows: 200 center, 202 A, 202 B, 200 C. Previously calculated preliminary slopes:

| Motor | Roll | Pitch | Yaw |
|---|---:|---:|---:|
| A | -0.006994°/count | -0.010613°/count | +0.002686°/count |
| B | +0.007596°/count | -0.011775°/count | approximately flat |
| C | approximately flat | approximately flat | +0.005544°/count |

These are historical preliminary calculations, not final calibration constants.

Earlier observations included A/B return hysteresis around 0.3–0.5°, and path-dependent Motor C yaw readings. Magnetometer/AHRS behavior may influence yaw.

## v0.4 Qwen test

User-reported physical test:
- Motor C initially moved.
- Script crashed a few movements into the run.
- `--tx-log` file was not created.
- Characterization did not complete.

Status: failed test. Initial movement does not validate the complete run.

## v0.4.1 ChatGPT test

### Source provenance

The original calibration source used for this characterization run is preserved in:

`src/calibration/`

Source version: v0.4.1.

The TX and WT901C sensor CSV files in `data/raw/` are the recorded outputs associated with this run.

The original source is retained for historical reference and reproducibility. Do not substitute a later calibration implementation when interpreting the v0.4.1 logs.

The existence of the source and associated logs does not independently establish that every feature of the script was validated.

User-reported physical test:
- Characterization completed.
- Both TX and sensor/readback CSV logs were produced.
- The uploaded logs are preserved in `data/raw/`.
- Dataset-specific findings are in `reports/V0.4.1_MOTOR_C_ANALYSIS.md`.

Do not infer that other untested features of v0.4.1 are physically validated.
