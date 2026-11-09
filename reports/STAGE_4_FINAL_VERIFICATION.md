# Stage 4 — Final Baseline Specification Verification

**Date:** 2026-11-08  
**Project:** Linux DOF Reality H3 Engineering Handoff  
**Version:** v0.4.1  
**Status:** Final Verification Complete  
**Workflow Stage:** Stage 4 of OpenSpec adoption  

---

## Executive Summary

**Verification Result:** **APPROVE BASELINE**

All seven baseline specifications have been verified against the actual v0.4.1 source code. The specifications accurately describe the implemented behavior.

**Verification Method:** Read-only examination of specifications against source code, tests, and documentation.

**Files Verified:**
- All seven specifications in `specs/`
- Source code: `src/calibration/h3_characterize.py`
- Test code: `src/calibration/test_v04.py`

---

## Verification Results by Specification

### SM-01: SMC3 Serial Communication

**Status:** ✓ ACCURATE

| Claim | Verification | Evidence |
|-------|--------------|----------|
| H3 port has no default | ✓ ACCURATE | Line 462: `parser.add_argument("--port", help="...")` - no default specified |
| WT901C port default is `/dev/ttyUSB0` | ✓ ACCURATE | Line 463: `parser.add_argument("--wt-port", default="/dev/ttyUSB0")` |
| H3 baud rate is 500000 | ✓ ACCURATE | Lines 36, 572: `SMC3_BAUD = 500000` and `factory(h3_port, SMC3_BAUD, ...)` |
| WT901C baud rate is 9600 | ✓ ACCURATE | Lines 37, 582: `WT_BAUD = 9600` and `factory(args.wt_port, WT_BAUD, ...)` |
| Two separate serial connections | ✓ ACCURATE | Lines 572, 582: H3 and WT901C opened separately |
| 2-second Arduino USB reset delay | ✓ ACCURATE | Lines 572-574: `time.sleep(2.0)` after H3 port open |
| pyserial is external dependency | ✓ ACCURATE | Lines 31-34: `try: import serial` with fallback |
| Standard library modules listed | ✓ ACCURATE | Lines 21-29: All modules accounted for |

**Correction Applied:** Dependencies section updated to correctly list pyserial and standard library modules.

---

### SM-02: Motor Command Protocol

**Status:** ✓ ACCURATE

| Claim | Verification | Evidence |
|-------|--------------|----------|
| Frame format: `[<motor><high><low>]` | ✓ ACCURATE | Line 201: `bytes((91, ord(motor), (position >> 8) & 255, position & 255, 93))` |
| Position range 0-1023 | ✓ ACCURATE | Lines 39-40, 200: `MIN_POS = 0`, `MAX_POS = 1023`, bounds checking |
| Center position = 512 | ✓ ACCURATE | Line 38: `CENTER = 512` |
| Readback commands lowercase | ✓ ACCURATE | Lines 44-48: `[rda]`, `[rdb]`, `[rdc]` |
| Response handling raw bytes only | ✓ ACCURATE | Lines 173-174: Response logged as hex only |

---

### SM-03: Readback Polling

**Status:** ✓ ACCURATE

| Claim | Verification | Evidence |
|-------|--------------|----------|
| Synchronous polling (no thread) | ✓ ACCURATE | Line 92: `"""Synchronous SMC3 readback; the main thread exclusively owns H3 serial I/O."""` |
| Serial ownership by main thread | ✓ ACCURATE | Line 92, Lines 572-584 |
| Polling interval configurable | ✓ ACCURATE | Lines 94-95, 481: `timeout=0.10`, `interval=0.25` defaults |
| Polling timeout configurable | ✓ ACCURATE | Lines 94-95, 480: `--readback-timeout` argument |
| Logs raw bytes only | ✓ ACCURATE | Lines 173-174: Response logged as hex |
| No position extraction | ✓ ACCURATE | Lines 173-174: Only hex logged |

---

### SM-04: WT901C Sensor Acquisition

**Status:** ✓ ACCURATE

| Claim | Verification | Evidence |
|-------|--------------|----------|
| Daemon thread for acquisition | ✓ ACCURATE | Line 309: `threading.Thread(..., daemon=True)` |
| Thread name "wt901c" | ✓ ACCURATE | Line 309: `name="wt901c"` |
| WIT packet format 11 bytes | ✓ ACCURATE | Line 41: `FRAME_LEN = 11` |
| Packet types 0x51-0x54 | ✓ ACCURATE | Lines 279-288: ACCEL, GYRO, ANGLE, MAG |
| Scale factors correct | ✓ ACCURATE | Lines 280-287: All scales documented |
| Samples queued only on ANGLE | ✓ ACCURATE | Lines 362-364: `if typ == 0x53:` |
| All packet types in latest | ✓ ACCURATE | Line 360: `self.latest[typ] = ...` |

---

### SM-05: Logging and CSV Output

**Status:** ✓ ACCURATE

| Claim | Verification | Evidence |
|-------|--------------|----------|
| TX Logger CSV schema | ✓ ACCURATE | Lines 64-67: Header row matches |
| Readback Logger CSV schema | ✓ ACCURATE | Lines 109-113: Header row matches |
| Main output CSV schema | ✓ ACCURATE | Lines 367-374: Field names match |
| Mode "x" exclusive creation | ✓ ACCURATE | Lines 62, 107, 595: `open("x", newline="")` |
| Raises FileExistsError if exists | ✓ ACCURATE | Lines 510, 518: Validation raises FileExistsError; mode "x" also raises |
| No timestamp synchronization | ✓ ACCURATE | Lines 79-83, 169-175, 385: Each uses own timestamp source |
| All files use newline="" | ✓ ACCURATE | Lines 62, 107, 595: `newline=""` in all open() calls |

**Correction Applied:** File mode "x" behavior corrected to accurately describe that it raises FileExistsError if file exists (does not truncate).

---

### SM-06: CLI and Execution Flow

**Status:** ✓ ACCURATE

| Claim | Verification | Evidence |
|-------|--------------|----------|
| All CLI arguments documented | ✓ ACCURATE | Lines 462-483: All arguments present |
| Argument defaults accurate | ✓ ACCURATE | Lines 463-483: All defaults match specification |
| Execution sequence correct | ✓ ACCURATE | Lines 460-687: Sequence matches |
| Validation checks documented | ✓ ACCURATE | Lines 486-503: All validations present |
| Context manager usage | ✓ ACCURATE | Lines 566-580: TXLogger and ReadbackPoller usage |

---

### SM-07: Threading and Lifecycle

**Status:** ✓ ACCURATE

| Claim | Verification | Evidence |
|-------|--------------|----------|
| Main thread synchronous | ✓ ACCURATE | Lines 460-687: All main execution |
| WT901CReader daemon thread | ✓ ACCURATE | Line 309: `daemon=True` |
| Thread lifecycle methods | ✓ ACCURATE | Lines 308-325: start(), stop(), discard_samples(), pop_samples() |
| Thread safety with lock | ✓ ACCURATE | Lines 303, 359-364: `threading.Lock` usage |
| Context managers | ✓ ACCURATE | Lines 60-74, 106-121: __enter__ and __exit__ |

---

## Cross-Specification Consistency

| Area | Consistency | Notes |
|------|-------------|-------|
| Serial port ownership | ✓ CONSISTENT | SM-01 correctly identifies two separate ports |
| Motor command path | ✓ CONSISTENT | SM-02 and SM-06 align |
| Readback path | ✓ CONSISTENT | SM-02, SM-03, SM-06 align |
| WT901C acquisition | ✓ CONSISTENT | SM-01, SM-04, SM-07 align |
| Logging behavior | ✓ CONSISTENT | SM-05 accurately references SM-03 |
| Timestamp handling | ✓ CONSISTENT | SM-05 correctly notes no synchronization |
| Threading model | ✓ CONSISTENT | SM-04 and SM-07 align on daemon thread |
| File creation mode | ✓ CONSISTENT | SM-05 accurately describes "x" mode |
| Dependencies | ✓ CONSISTENT | SM-01 correctly lists all dependencies |

---

## Corrections Verified

### Applied Corrections

1. **SM-01 Dependencies (Critical - Corrected)**
   - **Issue:** Claimed "Python standard library only" while using pyserial
   - **Correction:** Updated to list pyserial and standard library modules
   - **Evidence:** Lines 31-34, 21-29 in h3_characterize.py

2. **SM-01 H3 Port Default (Minor - Corrected)**
   - **Issue:** Incorrectly stated `/dev/ttyUSB0` as default
   - **Correction:** Updated to "None (requires explicit value)"
   - **Evidence:** Line 462 shows no default specified

3. **SM-01 Read Timeout (Minor - Clarified)**
   - **Issue:** Did not clarify timeout is passed to serial constructor
   - **Correction:** Added "(passed to serial constructor)" clarification
   - **Evidence:** Line 572: `timeout=0.5, write_timeout=0.5`

4. **SM-05 File Mode "x" (Minor - Corrected)**
   - **Issue:** Contradictory claim that mode "x" both "fails if exists" AND "truncates if exists"
   - **Correction:** Clarified that mode "x" raises FileExistsError if file exists (does not truncate)
   - **Evidence:** Lines 510, 518; mode "x" behavior

---

## v0.4.1 vs v0.3.5.1 Distinctions

The specifications correctly describe v0.4.1 behavior, not v0.3.5.1:

| Feature | v0.3.5.1 | v0.4.1 | Specification |
|---------|----------|--------|---------------|
| CommandHub queue | Used for all SMC3 writes | Bypassed entirely | SM-02: Direct sends |
| Hybrid queue design | FIFO across motor slots | No queue | SM-06: Direct send_all calls |
| Serial port architecture | Single shared port | Two separate ports | SM-01: H3 and WT901C separate |
| Readback polling | Asynchronous thread | Synchronous | SM-03: "main thread exclusively owns" |
| WT901C acquisition | Separate thread | Separate thread | SM-04: Daemon thread |

**Verification:** All specifications describe v0.4.1 implementation, not v0.3.5.1.

---

## Unresolved Questions (Genuine Issues)

The following questions remain unresolved in the source code and are accurately documented:

| ID | Description | Status | Specification |
|----|-------------|--------|---------------|
| UQ-02 | Readback response format not decoded | Unresolved | SM-02: Raw bytes only logged |
| UQ-03 | WT901C sampling rate not configurable | Unresolved | SM-04: Loop frequency not documented |
| UQ-04 | No timestamp synchronization between logs | Documented | SM-05: Each uses own timestamp source |

**Note:** UQ-01 (Serial port defaults) is now documented as an observation, not an unresolved issue.

---

## Validation Results

### Source Code Verification

**Status:** ✓ COMPLETE

Verified against:
- `src/calibration/h3_characterize.py` (HEAD)
- `src/calibration/test_v04.py` (HEAD)
- Existing data files

**Verification Methods:**
- Direct source code examination
- Cross-referencing with test suite behavior
- Validating against existing data files
- Distinguishing implemented behavior from documented intent

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

### Working Tree Integrity

**Status:** ✓ PRESERVED

**Not Modified:**
- All source files in `src/calibration/`
- All files in `analysis/`, `docs/`, `data/`, `reports/`
- `MANIFEST.sha256`
- `openspec/config.yaml`

**Pre-existing Modifications Preserved:**
- `src/calibration/smc3_readback_diagnostic.py` (M)
- `src/calibration/test_readback_diagnostic.py` (M)

---

## Final Recommendation

### **APPROVE BASELINE**

**Rationale:**
1. All seven specifications accurately describe the v0.4.1 implementation
2. All corrections have been applied and verified
3. Cross-specification consistency verified
4. No factual inaccuracies remain
5. Unresolved questions are accurately documented
6. v0.4.1 behavior correctly distinguished from v0.3.5.1

**Specifications Approved:**
- ✓ SM-01: SMC3 Serial Communication
- ✓ SM-02: Motor Command Protocol
- ✓ SM-03: Readback Polling
- ✓ SM-04: WT901C Sensor Acquisition
- ✓ SM-05: Logging and CSV Output
- ✓ SM-06: CLI and Execution Flow
- ✓ SM-07: Threading and Lifecycle

---

## Files Modified During Verification

**None.** This verification was read-only.

**Files Corrected (Previous Stage):**
- `specs/sm01_smc3_serial_communication.md` (3 corrections)
- `specs/sm05_logging_and_csv_output.md` (3 corrections)
- `reports/STAGE_4_SPECIFICATION_REVIEW.md` (reconciliation)

**Files Created:**
- `reports/STAGE_4_FINAL_VERIFICATION.md` (this file)

---

## Summary

**Verification Result:** ✓ ALL SPECIFICATIONS ACCURATE

**Corrections Required:** None

**Recommendation:** APPROVE BASELINE

**Next Step:** Proceed to Stage 5 — Specification Acceptance

---

**Status:** Final verification complete. Baseline specifications approved.
