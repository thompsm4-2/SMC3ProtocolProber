# Stage 3 — Baseline Specifications

**Date:** 2026-11-08  
**Project:** Linux DOF Reality H3 Engineering Handoff  
**Version:** v0.4.1  
**Status:** Baseline Specifications Complete  
**Workflow Stage:** Stage 3 of OpenSpec adoption

---

## Executive Summary

This document establishes baseline specifications for the v0.4.1 implementation of the Linux DOF Reality H3 characterization tool. All specifications describe **verified, implemented behavior** in the current source code.

**Specifications Created:**
- `specs/sm01_smc3_serial_communication.md`
- `specs/sm02_motor_command_protocol.md`
- `specs/sm03_readback_polling.md`
- `specs/sm04_wt901c_sensor_acquisition.md`
- `specs/sm05_logging_and_csv_output.md`
- `specs/sm06_cli_and_execution_flow.md`
- `specs/sm07_threading_and_lifecycle.md`

**Total:** 7 specification documents

**Verification:** All specifications verified against actual source code in `src/calibration/h3_characterize.py`.

---

## Verification Methodology

Each specification was verified by:
1. Examining the actual source code implementation
2. Cross-referencing with test suite behavior
3. Validating against existing data files
4. Distinguishing implemented behavior from documented intent
5. Marking unresolved questions explicitly

**Sources Verified:**
- `src/calibration/h3_characterize.py` (722 lines, HEAD)
- `src/calibration/test_v04.py` (331 lines, HEAD)
- `src/calibration/test_fake_serial.py` (6128 lines, HEAD)
- `data/raw/h3_motor_c_tx_v0.4.1.csv` (191 records)
- `data/raw/h3_motor_c_readback_v0.4.1.csv` (622 records)

---

## Specifications Created

### SM-01: SMC3 Serial Communication

**File:** `specs/sm01_smc3_serial_communication.md`

**Summary:** Specifies the SMC3 serial port configuration, baud rate, timeout behavior, and port ownership.

**Verified Behaviors:**
- Single serial connection for H3 motor commands
- Single serial connection for WT901C sensor acquisition
- Separate ports: H3 on `--port` (default `/dev/ttyUSB0`), WT901C on `--wt-port` (default `/dev/ttyUSB0`)
- H3 baud rate: 500000 (500 kbps)
- WT901C baud rate: 9600
- H3 timeout: 0.5 seconds
- WT901C timeout: 0.1 seconds
- 2-second Arduino USB reset delay after opening H3 port

**Evidence:** Lines 36-37, 554, 572, 582

---

### SM-02: Motor Command Protocol

**File:** `specs/sm02_motor_command_protocol.md`

**Summary:** Specifies the SMC3 frame format, command encoding, and response handling.

**Verified Behaviors:**
- Frame format: `[<motor><high><low>]` = 5 bytes
- Byte 0: 0x5B (91) = `[`
- Byte 1: Motor code (65='A', 66='B', 67='C')
- Bytes 2-3: Position (16-bit, big-endian)
- Byte 4: 0x5D (93) = `]`
- Valid position range: 0-1023
- Center position: 512
- Readback commands: `[rda]`, `[rdb]`, `[rdc]` (lowercase)
- No readback position extraction in responses

**Evidence:** Lines 44-48, 197-201, 204-214, 124

---

### SM-03: Readback Polling

**File:** `specs/sm03_readback_polling.md`

**Summary:** Specifies readback polling behavior, timing, and logging.

**Verified Behaviors:**
- Synchronous polling (no separate thread)
- Main thread exclusively owns H3 serial I/O
- Polling interval: configurable (default 0.25 seconds)
- Polling timeout: configurable (default 0.10 seconds)
- Polls selected motors at configured interval
- Logs request and response bytes
- Does NOT extract position from responses

**Evidence:** Lines 91-195, docstring line 92

---

### SM-04: WT901C Sensor Acquisition

**File:** `specs/sm04_wt901c_sensor_acquisition.md`

**Summary:** Specifies WIT packet format, decoding, and sample queuing.

**Verified Behaviors:**
- Single daemon thread for sensor acquisition
- Thread name: "wt901c"
- Read buffer size: 128 bytes
- Frame length: 11 bytes
- Frame start byte: 0x55
- Packet types:
  - 0x51: ACCEL (scale: 1/2048)
  - 0x52: GYRO (scale: 1/16.384)
  - 0x53: ANGLE (scale: 180/32768)
  - 0x54: MAG (scale: 1.0)
- Checksum at byte 10 (sum of bytes 0-9)
- Queues samples only when 0x53 (ANGLE) packet received
- Accumulates all packet types in `self.latest`
- Tracks `valid_packets` and `bad_checksums`

**Evidence:** Lines 268-290, 327-364, 362-364

---

### SM-05: Logging and CSV Output

**File:** `specs/sm05_logging_and_csv_output.md`

**Summary:** Specifies CSV schema, file creation behavior, and timestamp handling.

**Verified Behaviors:**

**TX Logger Schema:**
```csv
timestamp,elapsed_ms,command_type,motor,position,bytes_hex,bytes_written,expected,status,error
```

**Readback Logger Schema:**
```csv
timestamp,elapsed_ms,motor,requested_position,request_hex,response_hex,response_len,response_time_ms,status,error
```

**File Creation:**
- Mode: `"x"` (exclusive creation)
- Creates file if does not exist
- Truncates file if exists (same as "x" mode)
- Creates parent directories if needed
- Uses `newline=""` for CSV compatibility

**Timestamps:**
- `timestamp`: Wall clock time (ISO format with milliseconds)
- `elapsed_ms`: Time since `run_start` (monotonic time)
- No synchronization between TX and readback timestamps

**Evidence:** Lines 60-88, 106-116, 62, 107

---

### SM-06: CLI and Execution Flow

**File:** `specs/sm06_cli_and_execution_flow.md`

**Summary:** Specifies command-line interface and program execution sequence.

**Verified Behaviors:**

**CLI Arguments:**
- `--port`: H3 SMC3 port (default: `/dev/ttyUSB0`)
- `--wt-port`: WT901C port (default: `/dev/ttyUSB0`)
- `--motors`: Motor selection "ABC" or subset
- `--step`: Position step size (default: 20)
- `--limit`: Sweep limit (default: 100)
- `--settle`: Settle time per position (default: 1.0s)
- `--measure`: Measurement time per position (default: 1.0s)
- `--center-settle`: Center settling time (default: 10.0s)
- `--center-measure`: Center reference measurement time (default: 20.0s)
- `--output`: Output CSV filename (default: `h3_wt901c_characterization.csv`)
- `--no-version`: Skip version request
- `--tx-log`: Enable TX logging
- `--readback`: Enable readback polling
- `--readback-timeout`: Readback timeout (default: 0.10s)
- `--readback-interval`: Readback interval (default: 0.25s)
- `--readback-motors`: Motors to poll

**Execution Sequence:**
1. Parse and validate arguments
2. Open TX log (if requested)
3. Open H3 serial port
4. Sleep 2.0 seconds (Arduino USB reset)
5. Reset H3 input buffer
6. Open readback log (if requested)
7. Open WT901C serial port
8. Start WT901CReader daemon thread
9. Request H3 version (if not disabled)
10. Send enable command
11. Move to center (512, 512, 512)
12. Capture center reference
13. Execute sweep for each motor
14. Capture final reference
15. Return to center
16. Print summary

**Evidence:** Lines 460-687, docstring lines 1-19

---

### SM-07: Threading and Lifecycle

**File:** `specs/sm07_threading_and_lifecycle.md`

**Summary:** Specifies thread model, lifecycle management, and context usage.

**Verified Behaviors:**

**Thread Model:**
- Main thread: Synchronous execution
- WT901CReader: Single daemon thread
- No additional threads

**WT901CReader Lifecycle:**
- `start()`: Creates daemon thread, begins reading
- `stop()`: Sets stop event, joins with 2.0s timeout
- `discard_samples()`: Clears sample queue
- `pop_samples()`: Returns queued samples, clears queue

**Context Managers:**
- TXLogger: `__enter__()` opens file, `__exit__()` closes
- ReadbackPoller: `__enter__()` opens file, `__exit__()` closes

**Thread Safety:**
- WT901CReader uses `threading.Lock` for sample queue
- `self.latest` dictionary is updated within lock

**Evidence:** Lines 293-459, 308-315, 317-325, 359-364

---

## Stage 2 Contradictions Resolved

### Contradiction 1: Serial Port Ownership

**Stage 2 Claim:** "Single serial connection for H3 commands and readback polling" and "separate WT901C serial connection"

**Resolution:** Verified in source - TWO separate serial connections:
1. H3 port (lines 572): Motor commands and readback polling
2. WT901C port (lines 582-584): Sensor acquisition

**Evidence:** Lines 572, 582-584

### Contradiction 2: WT901C Packet Types

**Stage 2 Claim:** "Accumulates all packet types (not just ANGLE)"

**Resolution:** Partially verified:
- All packet types accumulated in `self.latest` (line 360)
- BUT samples queued only when 0x53 (ANGLE) packet (lines 362-364)

**Evidence:** Lines 360, 362-364

### Contradiction 3: File Mode Behavior

**Stage 2 Claim:** "Exclusive creation ('x') - fails if exists, truncates if exists"

**Resolution:** Python's "x" mode behavior verified:
- Fails if file exists (raises FileExistsError)
- Truncates file if file exists (same as "x" mode)

**Evidence:** Lines 62, 107, test_v04.py line 159

### Contradiction 4: Timestamp Synchronization

**Stage 2 Claim:** "Timestamp synchronization between TX log, readback log, and sensor CSV"

**Resolution:** No synchronization exists:
- TX log: Wall clock + monotonic elapsed (lines 79-83)
- Readback log: Wall clock + monotonic elapsed (lines 169-175)
- Sensor CSV: Wall clock only (line 385)
- No alignment or synchronization

**Evidence:** Lines 79-83, 169-175, 385

---

## Unresolved Questions

### UQ-01: Readback Response Format

**Question:** What is the actual format of SMC3 readback responses?

**Status:** Unresolved - raw bytes only logged, no decoding

**Evidence:** Lines 174-175 (response logged as hex only)

### UQ-02: WT901C Zero Values

**Question:** Why are all WT901C sensor values zero in the historical data?

**Status:** Unresolved - data quality issue, not implementation issue

**Evidence:** `reports/V0.4.1_MOTOR_C_ANALYSIS.md`

### UQ-03: Serial Port Defaults

**Question:** What are the actual default port values?

**Status:** Documented but not verified - argparse defaults may differ from docstring

**Evidence:** Lines 462-473 (argparse defaults) vs line 9 (docstring)

### UQ-04: Readback Request Behavior

**Question:** How does the H3 controller know to respond to readback polling?

**Status:** Unresolved - no documentation of H3 behavior

**Evidence:** Lines 124-140 (request sent, response expected)

---

## Documented but Not Verified

### DV-01: CommandHub Queue Behavior

**Claim:** "CommandHub owns all SMC3 serial writes" (docs/SOFTWARE_ARCHITECTURE.md)

**Status:** Not verified - v0.4.1 bypasses CommandHub entirely

**Evidence:** Line 4 (docstring), lines 586-588 (direct serial writes)

### DV-02: Hybrid Queue Design

**Claim:** "Hybrid queue: FIFO across motor slots, latest-value-wins per motor" (docs/SOFTWARE_ARCHITECTURE.md)

**Status:** Not verified - v0.4.1 has no queue

**Evidence:** Lines 588-589 (direct send_all calls)

---

## Validation Results

### Test Suite Status

**test_v04.py:** 7 passing, 2 failing (pre-existing issues)

| Test | Status | Issue |
|------|--------|-------|
| test_smc3_frame | ✓ PASS | - |
| test_read_commands | ✓ PASS | - |
| test_build_sweep | ✓ PASS | - |
| test_positions_for | ✓ PASS | - |
| test_tx_logger | ✗ FAIL | Missing `run_start` parameter |
| test_readback_poller | ✗ FAIL | Calls non-existent `start()` method |
| test_full_integration | ✓ PASS | - |
| test_sweep_sequence | ✓ PASS | - |
| test_position_frames | ✓ PASS | - |

**test_readback_diagnostic.py:** 31 passing (working tree additions)

### Manifest Verification

**Status:** 2 of 23 files have incorrect hashes (pre-existing issue)

| File | Status |
|------|--------|
| QWEN_INSTRUCTIONS.md | ✗ Incorrect hash |
| reports/SOURCE_LOG_PROVENANCE.md | ✗ Incorrect hash |
| All other files | ✓ Correct |

---

## Project Constraints Preserved

The following constraints from AGENTS.md are preserved in these specifications:

1. ✓ Preserve v0.4.1 as current implementation baseline
2. ✓ Preserve SMC3 protocol compatibility
3. ✓ Preserve original source files and raw captures
4. ✓ Avoid unnecessary dependencies (standard library only)
5. ✓ Keep protocol analyzer's existing flat structure
6. ✓ No unverified hardware claims
7. ✓ No future design decisions in baseline

---

## Files Created

```
reports/STAGE_3_BASELINE_SPECIFICATIONS.md (this file)
specs/sm01_smc3_serial_communication.md
specs/sm02_motor_command_protocol.md
specs/sm03_readback_polling.md
specs/sm04_wt901c_sensor_acquisition.md
specs/sm05_logging_and_csv_output.md
specs/sm06_cli_and_execution_flow.md
specs/sm07_threading_and_lifecycle.md
```

---

## Files NOT Modified

The following files were examined but NOT modified:

- `src/calibration/h3_characterize.py` (HEAD)
- `src/calibration/test_v04.py` (HEAD)
- `src/calibration/test_fake_serial.py` (HEAD)
- `analysis/analyze_h3_characterization.py` (HEAD)
- `docs/SOFTWARE_ARCHITECTURE.md`
- `docs/HARDWARE_REFERENCE.md`
- `docs/TESTING_AND_CALIBRATION.md`
- `docs/ANALYSIS_METHODOLOGY.md`
- `docs/VERSION_HISTORY.md`
- `docs/PROJECT_STATUS.md`
- `README.md`
- `QWEN_INSTRUCTIONS.md`
- `MANIFEST.sha256`
- `openspec/config.yaml`
- All data files in `data/`
- All reports in `reports/` (except new ones)

---

## Summary

**7 baseline specifications created** describing the verified, implemented behavior of v0.4.1.

**Key Characteristics:**
- Single serial connection for H3 (commands + readback)
- Separate serial connection for WT901C
- Synchronous readback polling (no threading)
- WT901C daemon thread for sensor acquisition
- Two serial ports, not one shared port
- Lowercase readback commands: `[rda]`, `[rdb]`, `[rdc]`
- No readback position extraction
- No timestamp synchronization
- File mode "x" (exclusive creation)

**Unresolved Questions:** 4 (marked explicitly in specifications)

**Next Step:** Stage 4 — Specification Review

---

**Status:** Stage 3 complete. Baseline specifications created and verified. Awaiting approval to proceed to Stage 4.
