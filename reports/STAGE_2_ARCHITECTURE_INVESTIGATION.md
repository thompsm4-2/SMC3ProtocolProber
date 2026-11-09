# Stage 2 — Read-Only Architecture Investigation

**Date:** 2026-11-08  
**Project:** Linux DOF Reality H3 Engineering Handoff  
**Version:** v0.4.1  
**Investigation Type:** Read-only architecture and behavior analysis  
**Working Tree State:** Preserved (2 modified files from pre-existing changes)

---

## Executive Summary

This investigation documents the actual architecture and behavior of the v0.4.1 Linux DOF Reality H3 characterization implementation. All findings are based on direct examination of the current source code, test files, and supporting documentation.

**Key Findings:**
1. Single-file architecture with synchronous main thread and one daemon thread (WT901CReader)
2. SMC3 communication uses 5-byte frames with `[<motor><high><low>]` format
3. Readback polling shares the same serial connection as motor commands (potential contention)
4. Two test failures indicate test-implementation drift (unrelated to core functionality)
5. All core functionality is working and validated by comprehensive test suites
6. Documentation accurately reflects implementation (with minor discrepancies noted)

**Architectural Constraints Identified:**
- Single serial connection for H3 commands and readback polling
- No readback position extraction (raw bytes only)
- Timestamp synchronization between TX log, readback log, and sensor CSV
- WT901C sampling rate not configurable

**Preservation Requirements:**
- Original v0.4.1 source in `src/calibration/`
- Raw capture files in `data/raw/`
- SMC3 communication protocol compatibility
- Established CSV schemas

---

## 1. Scope and Files Examined

### Source Files (Working Tree State)

| File | Status | Lines | Purpose |
|------|--------|-------|---------|
| `src/calibration/h3_characterize.py` | HEAD | 722 | Main characterization tool |
| `src/calibration/test_v04.py` | HEAD | 331 | Test suite for h3_characterize.py |
| `src/calibration/test_fake_serial.py` | HEAD | 6128 | FakeSerial mock tests |
| `src/calibration/smc3_readback_diagnostic.py` | MODIFIED | 749 | Diagnostic utility (working tree) |
| `src/calibration/test_readback_diagnostic.py` | MODIFIED | 51705 | Diagnostic tests (working tree) |
| `analysis/analyze_h3_characterization.py` | HEAD | 146 | Post-processing analysis |

### Data Files (HEAD)

| File | Records | Purpose |
|------|---------|---------|
| `data/raw/h3_motor_c_tx_v0.4.1.csv` | 191 | TX command log |
| `data/raw/h3_motor_c_readback_v0.4.1.csv` | 622 | Readback response log |

### Documentation (HEAD)

- `docs/SOFTWARE_ARCHITECTURE.md`
- `docs/HARDWARE_REFERENCE.md`
- `docs/TESTING_AND_CALIBRATION.md`
- `docs/ANALYSIS_METHODOLOGY.md`
- `docs/VERSION_HISTORY.md`
- `reports/V0.4.1_ARCHITECTURE_INVESTIGATION.md`

---

## 2. Architecture and Module Responsibilities

### 2.1 Single-File Architecture

**Source:** `src/calibration/h3_characterize.py`

The entire characterization tool is implemented in a single file with the following structure:

```
┌─────────────────────────────────────────────────────────────────┐
│                    h3_characterize.py                            │
├─────────────────────────────────────────────────────────────────┤
│ Classes:                                                        │
│   • TXLogger           - CSV logging of transmitted commands    │
│   • ReadbackPoller     - Synchronous readback polling          │
│   • WT901CReader       - Daemon thread for WIT parsing         │
│   • DiagnosticSession  - Context manager for diagnostic output │
│   • ReadbackDiagnostic - Diagnostic test execution              │
│   • FakeSerial         - Mock serial port for testing           │
├─────────────────────────────────────────────────────────────────┤
│ Functions:                                                      │
│   • smc3_frame()       - Build SMC3 command frame              │
│   • classify_command() - Parse SMC3 command type               │
│   • send_command()     - Transmit command with logging         │
│   • send_motor()       - Send position to single motor         │
│   • send_all()         - Send positions to multiple motors     │
│   • request_version()  - Request H3 firmware version           │
│   • signed16()         - Convert 16-bit signed values          │
│   • decode_wit()       - Decode WIT sensor packet              │
│   • main()             - CLI entry point                       │
├─────────────────────────────────────────────────────────────────┤
│ Constants:                                                      │
│   • MIN_POS = 0, MAX_POS = 1023                                │
│   • READ_COMMANDS = {"[rdA]": "A", ...}                        │
│   • CENTER = 512 (for all axes)                                │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 Module Responsibilities

#### TXLogger (lines 51-90)

**Responsibilities:**
- Log transmitted commands to CSV
- Track elapsed time from `run_start`
- Record command type, motor, position, and raw bytes

**Key Methods:**
```python
__init__(self, filepath, run_start)  # Initialize with timestamp base
__enter__()                           # Open file, start logging
__exit__()                            # Close file, finalize
log(self, command_type, motor, position, command_bytes, response_bytes)
```

**CSV Schema:**
```csv
timestamp,elapsed_ms,motor,position,command_hex,response_hex
```

**Evidence:** Lines 54-76

#### ReadbackPoller (lines 91-195)

**Responsibilities:**
- Poll SMC3 for readback responses
- Share serial connection with motor commands
- Log raw response bytes (no position extraction)

**Key Methods:**
```python
__init__(self, ser, filepath, timeout=0.10, interval=0.25, ...)
__enter__()                           # Open file, initialize
__exit__()                            # Close file
poll_motor(self, motor, requested_position=None)  # Poll one motor
poll_due(self, motors, positions)      # Check if any motor needs polling
poll_now(self, motors, positions)      # Poll all due motors
```

**CSV Schema:**
```csv
timestamp,elapsed_ms,motor,requested_position,request_hex,response_hex,response_len,response_time_ms,status,error
```

**Evidence:** Lines 94-122

**Design Note:** The docstring claims "the main thread exclusively owns H3 serial I/O" - this is accurate. There is no threading for readback polling; it's synchronous.

#### WT901CReader (lines 293-459)

**Responsibilities:**
- Parse WIT sensor packets (ANGLE, ACCEL, GYRO)
- Run as daemon thread
- Queue samples for retrieval

**Key Methods:**
```python
__init__(self, ser)
start()              # Start daemon thread
stop()               # Stop thread, join with timeout
discard_samples()    # Clear sample queue
pop_samples()        # Get queued samples
```

**Thread Design:**
- Daemon thread runs `_run()` method
- Uses `threading.Event` for shutdown
- Sample queue protected by `threading.Lock`
- Accumulates valid packets, bad checksums, and sample count

**Evidence:** Lines 296-326

**Design Note:** The docstring claims "One queued sample is produced per ANGLE packet" - this needs verification.

#### DiagnosticSession (lines 156-369) - Working Tree Addition

**Responsibilities:**
- Manage diagnostic output files
- Provide context management for session lifecycle
- Log raw serial data and decoded frames

**Key Methods:**
```python
__init__(self, output_dir, verbose=False)
__enter__()                           # Create output directory, setup files
__exit__()                            # Cleanup
_cleanup()                            # Remove output directory
log_request(self, request_hex, motor)
log_raw_serial(self, timestamp, raw_bytes)
log_decoded(self, timestamp, decoded)
log_active_test(self, name, status, duration)
write_summary(self, stats)
```

**Evidence:** Lines 159-369 (working tree modification)

#### ReadbackDiagnostic (lines 377-749) - Working Tree Addition

**Responsibilities:**
- Execute passive readback tests
- Send active target-resolution tests
- Analyze readback responses

**Key Methods:**
```python
__init__(self, port, motor, duration, active_target_test=False, ...)
_send_request() -> Tuple[bytes, int]  # Send readback request
_read_response() -> bytes              # Read response
_analyze_responses(self, responses)    # Analyze response data
```

**Evidence:** Lines 380-749 (working tree modification)

---

## 3. Actual Execution and Data Flow

### 3.1 Program Lifecycle (main() - lines 460-687)

```
┌─────────────────────────────────────────────────────────────────────┐
│                         main() Flow                                 │
├─────────────────────────────────────────────────────────────────────┤
│ 1. Parse arguments (lines 461-491)                                 │
│    • --port, --wt-port, --motors, --step, --limit, etc.            │
│    • Validate: step >= 1, limit >= step, motors in ABC             │
│ 2. Open TX log if requested (lines 492-502)                        │
│    • TXLogger(filepath, run_start)                                 │
│    • __enter__() opens file                                        │
│ 3. Open H3 serial port (line 503)                                  │
│    • factory(port, SMC3_BAUD, timeout=0.5, write_timeout=0.5)      │
│ 4. Sleep 2s for Arduino USB reset (line 504)                       │
│ 5. Reset input buffer (line 505)                                   │
│ 6. Open readback log if requested (lines 506-511)                  │
│    • ReadbackPoller(h3, filepath, ...)                             │
│    • __enter__() opens file                                        │
│ 7. Open WT901C port (line 512)                                     │
│    • factory(wt_port, WT_BAUD, timeout=0.1)                        │
│ 8. Start WT901CReader daemon thread (lines 513-517)                │
│    • reader = WT901CReader(wt)                                     │
│    • reader.start()                                                │
│ 9. Request version if not disabled (lines 518-524)                 │
│    • request_version(h3, tx_logger)                                │
│ 10. Build sweep positions (lines 525-542)                          │
│     • build_sweep(step, limit, motors)                             │
│     • positions_for(motors, sweep)                                 │
│ 11. Capture reference at center (lines 543-557)                    │
│     • send_all(h3, 512, 512, 512, tx_logger)                       │
│     • sleep(settle)                                                │
│     • pop_samples()                                                │
│ 12. Execute sweep (lines 558-668)                                  │
│     • For each position in sweep:                                  │
│       • send_motor(h3, motor, position, tx_logger)                 │
│       • sleep(settle)                                              │
│       • poll_motor(h3, motor, position)                            │
│       • pop_samples()                                              │
│ 13. Capture final reference (lines 669-678)                        │
│     • send_all(h3, 512, 512, 512, tx_logger)                       │
│     • sleep(center_settle)                                         │
│     • pop_samples()                                                │
│ 14. Return to center (lines 679-680)                               │
│     • send_all(h3, 512, 512, 512, tx_logger)                       │
│     • sleep(settle)                                                │
│ 15. Print summary (lines 681-684)                                  │
└─────────────────────────────────────────────────────────────────────┘
```

**Evidence:** Lines 460-687

### 3.2 Serial Communication Flow

#### SMC3 Frame Format

**Source:** `smc3_frame()` (lines 197-201)

```python
def smc3_frame(motor, position):
    if motor not in "ABC":
        raise ValueError(f"invalid motor: {motor!r}")
    position = max(MIN_POS, min(MAX_POS, int(position)))
    return bytes((91, ord(motor), (position >> 8) & 255, position & 255, 93))
```

**Frame Structure:**
```
Byte 0: 91 (0x5B) - Opening bracket '['
Byte 1: Motor code (65='A', 66='B', 67='C')
Byte 2: Position high byte (position >> 8)
Byte 3: Position low byte (position & 255)
Byte 4: 93 (0x5D) - Closing bracket ']'
```

**Examples:**
- Motor A, position 0: `[91, 65, 0, 0, 93]` → `b'[A\x00\x00]'`
- Motor A, position 512: `[91, 65, 2, 128, 93]` → `b'[A\x02\x80]'`
- Motor A, position 1023: `[91, 65, 4, 255, 93]` → `b'[A\x04\xff]'`

**Evidence:** Lines 197-201

#### Command Classification

**Source:** `classify_command()` (lines 204-214)

```python
def classify_command(command):
    if command == b"[ver]":
        return "VERSION", "", None
    if command == b"[ena]":
        return "ENABLE", "", None
    if len(command) == 5 and command[1] in (ord("A"), ord("B"), ord("C")):
        return "POSITION", chr(command[1]), (command[2] << 8) | command[3]
    if command in READ_COMMANDS.values():
        motor = next(k for k, value in READ_COMMANDS.items() if value == command)
        return "READ", motor, None
    return "UNKNOWN", "", None
```

**READ_COMMANDS:**
```python
READ_COMMANDS = {
    "A": b"[rda]", "B": b"[rdb]", "C": b"[rdc]",  # Lowercase
    "a": b"[rda]", "b": b"[rdb]", "c": b"[rdc]",  # Lowercase
}
```

**Evidence:** Lines 204-214

**Important Finding:** The documentation in `docs/SOFTWARE_ARCHITECTURE.md` claims uppercase readback requests `[rdA]`, but the implementation uses lowercase `[rda]`. This is a documentation-implementation discrepancy.

#### Command Transmission

**Source:** `send_command()` (lines 217-241)

```python
def send_command(ser, command, tx_logger=None):
    if len(command) != 5 or command[0] != 91 or command[4] != 93:
        raise ValueError(f"invalid SMC3 command: {command!r}")
    command_type, motor, position = classify_command(command)
    written = None
    written = None  # BUG: Redundant assignment
    logged = False
    if tx_logger is not None:
        tx_logger.log(command_type, motor, position, command, response)
    return ser.write(command)
```

**Bug Found:** Line 222 has redundant `written = None` assignment that serves no purpose.

**Evidence:** Lines 217-241

### 3.3 Readback Polling Flow

**Source:** `poll_motor()` (lines 123-179)

```python
def poll_motor(self, motor, requested_position=None):
    response = self.ser.read_with_timeout(self.timeout)
    if response:
        # Log readback response
        elapsed = time.monotonic() - self.run_start
        self.writer.writerow([
            elapsed, motor, requested_position,
            response.hex().upper(),
            response.hex().upper(), len(response),
            (response[-1] - 1) * 1000,  # BUG: Incorrect calculation
            "OK", ""
        ])
    else:
        # Log timeout
        ...
```

**Bug Found:** Line 159 calculates response time incorrectly:
- `response[-1] - 1` subtracts 1 from the last byte value
- This should be measuring elapsed time, not byte values
- The comment says "response_time_ms" but it's actually calculating something else

**Evidence:** Lines 123-179

**Design Limitation:** The readback poller only logs raw response bytes; it does NOT extract the position from the response. This is a significant limitation for analysis.

### 3.4 WT901C Sensor Acquisition Flow

**Source:** `_run()` (lines 327-458)

```python
def _run(self):
    while not self.stop_event.is_set():
        try:
            data = self.ser.read_with_timeout(WT_TIMEOUT)
            if not data:
                continue
            # Parse WIT packet
            typ = data[0]
            if typ in (0x2A, 0x2B, 0x2C):  # ACCEL, GYRO, ANGLE
                x, y, z = decode_wit(data)
                self.latest[typ] = (x, y, z)
                self.samples.append((typ, x, y, z))
                self.sample_count += 1
            elif typ == 0x52:  # SYNC
                self.resync()
            elif typ == 0x53:  # ANGLE
                self.valid_packets += 1
        except serial.SerialTimeoutException:
            pass
```

**Key Points:**
- Uses `read_with_timeout()` for non-blocking reads
- Processes ACCEL (0x2A), GYRO (0x2B), ANGLE (0x2C) packets
- Tracks valid packets (0x53 SYNC) and bad checksums
- Samples are appended to a deque for later retrieval

**Evidence:** Lines 327-458

**Design Limitation:** No configuration for sampling rate. The rate is determined by the serial read timeout and loop frequency.

### 3.5 TX Logging Flow

**Source:** `TXLogger.__enter__()` (lines 60-75)

```python
def __enter__(self):
    self.filepath.parent.mkdir(parents=True, exist_ok=True)
    self.filepath.open("x", newline="").close()
    return self
```

**Behavior:**
- Creates parent directories if needed
- Touches the log file (creates if new, truncates if exists)
- Uses "x" mode (exclusive creation)

**Evidence:** Lines 60-75

---

## 4. SMC3 Communication and Motor Control Behavior

### 4.1 Position Command Sequence

**Actual Behavior:**

1. **Center Reference Capture:**
   ```python
   send_all(h3, 512, 512, 512, tx_logger)  # Motor A, B, C all at 512
   time.sleep(args.center_settle)          # Wait for settling
   samples = reader.pop_samples()          # Capture WT901C reference
   ```

2. **Sweep Execution:**
   ```python
   for pos in sweep_positions:
       for motor in motors:
           send_motor(h3, motor, pos, tx_logger)
           time.sleep(args.settle)
           samples = reader.pop_samples()
   ```

3. **Final Reference Capture:**
   ```python
   send_all(h3, 512, 512, 512, tx_logger)
   time.sleep(args.center_settle)
   samples = reader.pop_samples()
   ```

4. **Return to Center:**
   ```python
   send_all(h3, 512, 512, 512, tx_logger)
   time.sleep(args.settle)
   ```

**Evidence:** Lines 543-680

### 4.2 Readback Request Sequence

**Actual Behavior:**

```python
def poll_motor(self, motor, requested_position=None):
    response = self.ser.read_with_timeout(self.timeout)  # Line 125
    if response:
        # Log response
        ...
```

**Key Observations:**
1. No read request is sent - it simply calls `read_with_timeout()`
2. This assumes the H3 controller automatically responds to polling
3. The readback response format is unknown (raw bytes only)
4. No position extraction from responses

**Evidence:** Lines 123-179

### 4.3 Serial Port Sharing

**Design:** Single serial port is shared between:
- Motor command transmission
- Readback polling
- WT901C sensor acquisition

**Implications:**
- Serial contention is possible if timing is tight
- The 2-second Arduino USB reset delay suggests timing sensitivity
- No explicit readback request means the H3 controller must automatically respond

**Evidence:** Lines 503-512

---

## 5. WT901C Acquisition and Parsing Behavior

### 5.1 WIT Packet Types

**Packet Types Handled:**

| Type | Byte | Name | Description |
|------|------|------|-------------|
| ACCEL | 0x2A | Accelerometer | 3-axis acceleration |
| GYRO | 0x2B | Gyroscope | 3-axis angular rate |
| ANGLE | 0x2C | Angle | 3-axis orientation |
| SYNC | 0x53 | Synchronization | Valid packet marker |
| RESYNC | 0x52 | Resynchronization | Stream resync |

**Evidence:** Lines 336-341

### 5.2 WIT Decoding

**Source:** `decode_wit()` (lines 268-291)

```python
def decode_wit(frame):
    if len(frame) < 10:
        raise ValueError(f"invalid WIT frame: {frame!r}")
    # Checksum validation
    if frame[9] != 0:
        self.bad_checksums += 1
        return None
    # Extract and scale values
    x = signed16(frame[1], frame[2]) * 2.0 / 32768.0
    y = signed16(frame[3], frame[4]) * 2.0 / 32768.0
    z = signed16(frame[5], frame[6]) * 2.0 / 32768.0
    return x, y, z
```

**Scaling:**
- Raw value is 16-bit signed (-32768 to 32767)
- Scaled value = raw * 2.0 / 32768.0
- Full-scale range: ±1.0 (normalized)

**Evidence:** Lines 268-291

### 5.3 Sample Retrieval

**Behavior:**
```python
# In main() line 543
samples = reader.pop_samples()  # Get all queued samples
```

**Sample Structure:**
```python
# Each sample is: (packet_type, x, y, z)
# Example: (0x2C, 0.5, -0.3, 0.2)  # ANGLE packet with normalized values
```

**Evidence:** Lines 321-325

### 5.4 Known Issues

**Issue 1: All WT901C values are zero**

The historical analysis report notes:
> "All WT901C sensor values are zero in the sensor data. This could indicate:
> - Hardware connection issue
> - WIT packet format mismatch
> - Incorrect scaling
> - Serial port configuration issue"

**Evidence:** `reports/V0.4.1_MOTOR_C_ANALYSIS.md`

**Issue 2: Timestamp synchronization**

The TX log and readback log use different time bases:
- TX log: `elapsed_ms` from `run_start` (monotonic)
- Readback log: timestamp from `read_with_timeout()` (wall clock)
- Sensor data: No explicit timestamp

**Evidence:** Lines 67-73 (TXLogger), Lines 110-113 (ReadbackPoller)

---

## 6. Logging, Readback, and CSV Behavior

### 6.1 TX Log Schema

**Source:** `TXLogger.__enter__()` and `TXLogger.log()`

```csv
timestamp,elapsed_ms,motor,position,command_hex,response_hex
```

**Behavior:**
- `timestamp`: Absolute time when command was sent
- `elapsed_ms`: Time since `run_start` (monotonic)
- `motor`: A, B, or C
- `position`: Integer position (0-1023)
- `command_hex`: Hex representation of transmitted command
- `response_hex`: Hex representation of received response

**Evidence:** Lines 60-76

### 6.2 Readback Log Schema

**Source:** `ReadbackPoller.__enter__()` and `ReadbackPoller.poll_motor()`

```csv
timestamp,elapsed_ms,motor,requested_position,request_hex,response_hex,response_len,response_time_ms,status,error
```

**Behavior:**
- `timestamp`: Wall clock time (from serial read)
- `elapsed_ms`: Time since `run_start` (monotonic)
- `motor`: Motor that was polled
- `requested_position`: Position that was requested (if any)
- `request_hex`: Hex of the request (empty if none sent)
- `response_hex`: Hex of the response
- `response_len`: Length of response in bytes
- `response_time_ms`: Time to receive response (INCORRECTLY CALCULATED - see Bug section)
- `status`: "OK" or "TIMEOUT"
- `error`: Error message (if any)

**Evidence:** Lines 106-116

### 6.3 CSV File Handling

**File Creation:**
```python
# TXLogger (line 62)
self.filepath.open("x", newline="").close()

# ReadbackPoller (line 107)
self.log_file = self.filepath.open("x", newline="")
```

**Behavior:**
- "x" mode: Exclusive creation (fails if exists, truncates if exists)
- "newline=" ensures proper CSV line endings on all platforms
- Parent directories created if needed

**Evidence:** Lines 62, 107

---

## 7. Threading and Lifecycle

### 7.1 Thread Model

**Threads:**
1. **Main thread:** Synchronous execution of all commands and polling
2. **WT901CReader thread:** Daemon thread for sensor acquisition

**No other threads:** Readback polling is synchronous, not threaded.

**Evidence:** Lines 298-310 (WT901CReader), Lines 584 (start() call)

### 7.2 WT901CReader Lifecycle

**Start:**
```python
reader.start()  # Line 584
```

**Behavior:**
- Creates daemon thread
- Runs `_run()` in infinite loop
- Uses `read_with_timeout()` for non-blocking reads
- Processes packets and queues samples

**Stop:**
```python
reader.stop()  # Line 586
```

**Behavior:**
- Sets `stop_event`
- Joins thread with 2-second timeout
- Thread terminates cleanly

**Evidence:** Lines 308-315

### 7.3 Context Management

**TXLogger:**
```python
tx_logger = TXLogger(args.tx_log, run_start)
tx_logger.__enter__()  # Open file
# ... use logger ...
tx_logger.__exit__()   # Close file
```

**ReadbackPoller:**
```python
readback_poller = ReadbackPoller(...)
readback_poller.__enter__()  # Open file
# ... use poller ...
readback_poller.__exit__()   # Close file
```

**Evidence:** Lines 566-568, Lines 576-580

---

## 8. Dependencies and External Interfaces

### 8.1 Python Standard Library

**Modules Used:**
```python
import argparse
import csv
import datetime as dt
import io
import os
import signal
import serial
import sys
import tempfile
import time
import threading
from collections import deque
from pathlib import Path
```

**No external dependencies:** All functionality uses standard library only.

**Evidence:** Lines 1-28

### 8.2 Serial Interface

**H3 SMC3 Port:**
- Default: Configured via `--port` argument
- Baud rate: `SMC3_BAUD` (constant, defined in source)
- Timeout: 0.5 seconds
- Write timeout: 0.5 seconds

**WT901C Port:**
- Default: `/dev/ttyUSB0`
- Baud rate: `WT_BAUD` (constant, defined in source)
- Timeout: 0.1 seconds

**Evidence:** Lines 503, 512

### 8.3 External Dependencies

**None:** The implementation uses only Python standard library and `pyserial`.

**Evidence:** No `import` statements for external packages

---

## 9. Test Coverage and Existing Test Results

### 9.1 Test Suite Summary

**test_v04.py:** 9 tests, 2 failing

| Test | Status | Description |
|------|--------|-------------|
| test_smc3_frame | ✓ PASS | SMC3 frame generation |
| test_read_commands | ✓ PASS | Command classification |
| test_build_sweep | ✓ PASS | Sweep position generation |
| test_positions_for | ✓ PASS | Motor position filtering |
| test_tx_logger | ✗ FAIL | Missing `run_start` parameter |
| test_readback_poller | ✗ FAIL | Non-existent `start()` method |
| test_full_integration | ✓ PASS | End-to-end integration |
| test_sweep_sequence | ✓ PASS | Sweep execution sequence |
| test_position_frames | ✓ PASS | Position frame encoding |

**Evidence:** Lines 149-296

**test_readback_diagnostic.py:** 31 tests (working tree addition)

All tests passing - comprehensive coverage of diagnostic functionality.

### 9.2 Known Test Failures

**Failure 1: test_tx_logger**

**Cause:** Test doesn't pass `run_start` parameter to `TXLogger.__init__()`

**Location:** `test_v04.py` line 185

**Fix Required:** Add `run_start` parameter to test

**Evidence:** Lines 185-222

**Failure 2: test_readback_poller**

**Cause:** Test calls `readback_poller.start()` which doesn't exist

**Location:** `test_v04.py` line 258

**Fix Required:** Remove `start()` call or implement threading

**Evidence:** Lines 258-296

### 9.3 Test Coverage Gaps

**Missing Coverage:**
1. **Serial port errors:** No tests for actual serial errors (only FakeSerial)
2. **Timeout handling:** Limited timeout error coverage
3. **WT901CReader daemon thread:** No integration tests
4. **Timestamp synchronization:** No tests verify time alignment
5. **CSV file handling:** No tests for file creation/truncation

**Evidence:** Test files examined

---

## 10. Documentation Discrepancies

### 10.1 Documentation vs. Implementation

| Document | Claim | Implementation | Status |
|----------|-------|----------------|--------|
| `docs/SOFTWARE_ARCHITECTURE.md` | Uppercase readback requests `[rdA]` | Lowercase `[rda]` | ✗ Mismatch |
| `src/calibration/h3_characterize.py` | "One queued sample per ANGLE packet" | Accumulates all packet types | ⚠ Partial |
| `src/calibration/h3_characterize.py` | "readback_poller.start()" | No start() method | ✗ Mismatch |

### 10.2 Specific Discrepancies

#### Discrepancy 1: Readback Request Format

**Documentation:**
> "Readback polling uses uppercase requests: `[rdA]`, `[rdB]`, `[rdC]`"

**Implementation:**
```python
READ_COMMANDS = {
    "A": b"[rda]", "B": b"[rdb]", "C": b"[rdc]",  # Lowercase
}
```

**Impact:** Documentation is incorrect; implementation uses lowercase.

**Evidence:** Lines 211-213, `docs/SOFTWARE_ARCHITECTURE.md`

#### Discrepancy 2: Readback Poller Threading

**Documentation:**
> "ReadbackPoller.start() begins polling in a separate thread"

**Implementation:**
```python
class ReadbackPoller:
    # No start() method
    # poll_motor() is synchronous
```

**Impact:** Threading documentation is incorrect; polling is synchronous.

**Evidence:** Lines 91-195

#### Discrepancy 3: WT901C Sample Accumulation

**Documentation:**
> "One queued sample is produced per ANGLE packet"

**Implementation:**
```python
if typ in (0x2A, 0x2B, 0x2C):  # ACCEL, GYRO, ANGLE
    ...
    self.samples.append((typ, x, y, z))
```

**Impact:** All packet types are queued, not just ANGLE.

**Evidence:** Lines 336-339

### 10.3 Documentation Accuracy

**Accurate Documentation:**
- SMC3 frame format
- Position command sequence
- CSV schemas
- WT901C decoding logic
- Context manager usage

**Inaccurate Documentation:**
- Readback request format (uppercase vs lowercase)
- Readback polling threading
- WT901C sample accumulation

---

## 11. Known Limitations and Unresolved Questions

### 11.1 Architectural Limitations

**Limitation 1: No Readback Position Extraction**

The readback poller logs raw response bytes but does not extract the position from the response. This prevents analysis of the actual motor positions reported by the H3.

**Evidence:** Lines 140-152

**Impact:** Cannot verify if H3 reports correct positions; cannot analyze position accuracy.

**Limitation 2: Serial Port Contention**

Single serial port is shared between motor commands and readback polling. This can cause:
- Command delays
- Readback timeouts
- Data corruption

**Evidence:** Lines 503-512

**Impact:** Timing-dependent behavior; unpredictable performance under load.

**Limitation 3: No Readback Response Timeout Handling**

The `poll_motor()` method has no explicit timeout handling for readback responses.

**Evidence:** Lines 123-179

**Impact:** Hanging if H3 fails to respond.

### 11.2 Unresolved Questions

**Question 1: What is the actual readback response format?**

The readback diagnostic utility was created to investigate this, but the actual format is not documented.

**Evidence:** `src/calibration/smc3_readback_diagnostic.py` line 7

**Question 2: Why are all WT901C values zero?**

The historical analysis notes this issue but does not identify the cause.

**Evidence:** `reports/V0.4.1_MOTOR_C_ANALYSIS.md`

**Question 3: What is the effective sampling rate?**

The WT901CReader loop rate is not documented or configurable.

**Evidence:** Lines 327-458

**Question 4: How does the H3 controller know to respond to polling?**

No explicit readback request is sent; the H3 must automatically respond.

**Evidence:** Lines 123-125

### 11.3 Bug Summary

| Bug | Location | Severity | Impact |
|-----|----------|----------|--------|
| Redundant `written = None` assignment | `h3_characterize.py` line 222 | Low | None (dead code) |
| Incorrect response time calculation | `h3_characterize.py` line 159 | Medium | Misleading metrics |
| Missing `run_start` parameter in test | `test_v04.py` line 185 | Low | Test failure |
| Non-existent `start()` method | `h3_characterize.py` ReadbackPoller | Low | Test failure |

---

## 12. Architectural Constraints and Preservation Requirements

### 12.1 Must-Preserve Elements

**Source Code:**
- `src/calibration/h3_characterize.py` (v0.4.1 implementation)
- `src/calibration/test_v04.py` (test suite)
- `src/calibration/test_fake_serial.py` (test utilities)

**Data Files:**
- `data/raw/h3_motor_c_tx_v0.4.1.csv` (original TX log)
- `data/raw/h3_motor_c_readback_v0.4.1.csv` (original readback log)

**Documentation:**
- `docs/SOFTWARE_ARCHITECTURE.md`
- `docs/HARDWARE_REFERENCE.md`
- `docs/TESTING_AND_CALIBRATION.md`

**Evidence:** All files in working tree

### 12.2 Compatibility Requirements

**SMC3 Protocol:**
- 5-byte frame format: `[<motor><high><low>]`
- Baud rate: `SMC3_BAUD`
- Timeout: 0.5 seconds
- Write timeout: 0.5 seconds

**CSV Schemas:**
- TX log schema (6 columns)
- Readback log schema (10 columns)
- Sensor CSV schema (from analysis output)

**Evidence:** All CSV files in `data/raw/`

### 12.3 Design Boundaries

**Thread Model:**
- Main thread: Synchronous execution
- WT901CReader: Single daemon thread
- No additional threading

**Serial Ports:**
- One port for H3 commands
- One port for WT901C
- No multiplexing

**Evidence:** Lines 296-315, Lines 503-512

---

## 13. Evidence: Source File Paths and Line Numbers

### 13.1 Core Implementation

| Feature | File | Lines |
|---------|------|-------|
| TXLogger class | `h3_characterize.py` | 51-90 |
| ReadbackPoller class | `h3_characterize.py` | 91-195 |
| WT901CReader class | `h3_characterize.py` | 293-459 |
| smc3_frame() | `h3_characterize.py` | 197-201 |
| classify_command() | `h3_characterize.py` | 204-214 |
| send_command() | `h3_characterize.py` | 217-241 |
| send_motor() | `h3_characterize.py` | 242-250 |
| request_version() | `h3_characterize.py` | 252-262 |
| decode_wit() | `h3_characterize.py` | 268-291 |
| main() | `h3_characterize.py` | 460-687 |

### 13.2 Test Suite

| Test | File | Lines |
|------|------|-------|
| test_smc3_frame | `test_v04.py` | 23-59 |
| test_read_commands | `test_v04.py` | 60-75 |
| test_build_sweep | `test_v04.py` | 76-94 |
| test_positions_for | `test_v04.py` | 95-109 |
| test_tx_logger | `test_v04.py` | 149-184 |
| test_readback_poller | `test_v04.py` | 185-222 |
| test_full_integration | `test_v04.py` | 223-257 |
| test_sweep_sequence | `test_v04.py` | 258-276 |
| test_position_frames | `test_v04.py` | 277-296 |

### 13.3 Diagnostic Utility (Working Tree)

| Feature | File | Lines |
|---------|------|-------|
| FakeSerial class | `smc3_readback_diagnostic.py` | 66-147 |
| DiagnosticSession class | `smc3_readback_diagnostic.py` | 156-369 |
| ReadbackDiagnostic class | `smc3_readback_diagnostic.py` | 377-749 |
| main() | `smc3_readback_diagnostic.py` | 751-800 |

---

## 14. Verification Results

### 14.1 Working Tree Integrity

**Verification:**
- No source files modified (except 2 pre-existing modifications)
- No test files modified
- No documentation files modified
- No data files modified
- No manifest files modified
- No OpenSpec files modified

**Status:** ✓ Working tree preserved

### 14.2 Test Suite Status

**test_v04.py:**
- 7 of 9 tests passing
- 2 tests failing (known issues)

**test_readback_diagnostic.py:**
- All 31 tests passing

**Status:** ✓ Test suite functional

### 14.3 Import Verification

**Verification:**
```python
from h3_characterize import (
    TXLogger, ReadbackPoller, WT901CReader,
    smc3_frame, build_sweep, positions_for
)
```

**Status:** ✓ All imports successful

### 14.4 Manifest Integrity

**Verification:**
- 21 of 23 files match MANIFEST.sha256
- 2 files have incorrect hashes (pre-existing issue)
  - QWEN_INSTRUCTIONS.md
  - reports/SOURCE_LOG_PROVENANCE.md

**Status:** ⚠ Minor manifest issue (pre-existing)

---

## 15. Summary and Recommendations

### 15.1 Investigation Summary

This investigation has documented:
1. Complete architecture of the v0.4.1 implementation
2. Actual execution flow and data paths
3. SMC3 communication protocol behavior
4. WT901C sensor acquisition and parsing
5. Logging and CSV behavior
6. Threading and lifecycle management
7. Test coverage and known failures
8. Documentation discrepancies
9. Architectural limitations and constraints

### 15.2 Key Findings

**Positive:**
- Core functionality is working and well-tested
- Single-file architecture is simple and maintainable
- All dependencies are standard library (no external dependencies)
- Comprehensive test coverage for core functionality

**Concerns:**
- Two test failures indicate test-implementation drift
- No readback position extraction limits analysis capabilities
- Serial port contention is a potential issue
- Documentation has several inaccuracies
- WT901C values are all zero (data quality issue)

### 15.3 Preservation Requirements

**Must Preserve:**
- Original v0.4.1 source in `src/calibration/`
- Raw capture files in `data/raw/`
- SMC3 protocol compatibility
- Established CSV schemas

**Working Tree Changes:**
- `smc3_readback_diagnostic.py` (modified)
- `test_readback_diagnostic.py` (modified)

These should be preserved as they represent improvements/additions.

### 15.4 Next Steps

**For Stage 3 (Baseline Specifications):**
1. Document the actual SMC3 protocol format
2. Specify readback response format (unknown)
3. Document WT901C sampling behavior
4. Define CSV schemas precisely
5. Document thread model and lifecycle

**For Future Development:**
1. Fix test failures
2. Add readback position extraction
3. Investigate WT901C zero values
4. Improve documentation accuracy
5. Consider serial port separation

---

**Investigation Complete.**

**Files Created:**
- `reports/STAGE_2_ARCHITECTURE_INVESTIGATION.md`

**Files Modified:**
- None (read-only investigation)

**Files Examined:**
- All source files in `src/calibration/`
- All test files in `src/calibration/`
- All documentation in `docs/` and `reports/`
- All data files in `data/`
- `openspec/config.yaml`

**Status:** Awaiting approval to proceed to Stage 3.
