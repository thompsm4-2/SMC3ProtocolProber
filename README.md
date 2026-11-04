# Linux DOF Reality H3 Engineering Project

**Portable handoff:** v1.0  
**Prepared:** 2026-11-02  
**Current characterization reference:** v0.4.1 Motor C run  
**Purpose:** Keep ChatGPT and a local Qwen/OpenCode assistant aligned on hardware facts, software architecture, experimental evidence, and reproducible analysis.

## Start here

1. Read `docs/PROJECT_STATUS.md`.
2. Read `docs/HARDWARE_REFERENCE.md` and `docs/SOFTWARE_ARCHITECTURE.md` before changing control code.
3. Read `docs/ANALYSIS_METHODOLOGY.md` before analyzing logs.
4. Read `QWEN_INSTRUCTIONS.md` before assigning work to the local LLM.
5. Review `reports/V0.4.1_MOTOR_C_ANALYSIS.md` for the first dataset-specific findings.

## Package contents

- `src/calibrate/` — original v0.4.1 calibration source code, preserved as a historical reference.
- `docs/` — project and hardware reference.
- `analysis/analyze_h3_characterization.py` — standard-library-only repeatable CSV analysis utility.
- `data/raw/` — original user-provided v0.4.1 logs, copied unchanged from the uploaded ZIP.
- `data/derived/` — generated group summaries and JSON analysis output.
- `reports/` — dataset-specific report.
- `MANIFEST.sha256` — SHA-256 hashes for package files (excluding the manifest itself).

## Directory structure

```text
Linux_DOF_Reality_H3_Engineering_Handoff_v1.0/
├── src/
│   └── calibration/
│       └── h3_characterize.py
│       └── README.md
│       └── test_fake_serial.py
│       └── test_v04.py
├── analysis/
│   └── analyze_h3_characterization.py
├── data/
│   ├── raw/
│   └── derived/
├── docs/
├── reports/
├── README.md
├── QWEN_INSTRUCTIONS.md
└── MANIFEST.sha256

## Re-run the analysis

From the package root:

```bash
python analysis/analyze_h3_characterization.py \
  --tx data/raw/h3_motor_c_tx_v0.4.1.csv \
  --sensor data/raw/h3_motor_c_readback_v0.4.1.csv \
  --out data/derived
```

The script uses only the Python standard library. It writes:
- `analysis_summary.json`
- `sensor_group_summary.csv`
- `analysis_report.md`

## Evidence rules

- Never overwrite original logs.
- Distinguish commanded position from measured platform orientation.
- A successful serial write is not proof of controller execution or physical movement.
- Label conclusions as measured, calculated, source-inspected, software-tested, physically tested, or hypothesis.
- Preserve exact source versions and test records.
- If two assistants disagree, compare exact files and reproducible outputs rather than relying on either assistant's authority.

## Important limitation

The current v0.4.1 files contain TX write records and WT901C sensor samples. The TX file records `[rdc]` request transmissions, but it does not include the controller's returned response bytes. Do not describe the sensor CSV as an SMC3 response capture.
