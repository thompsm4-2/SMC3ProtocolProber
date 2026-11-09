# Specification SM-01: SMC3 Serial Communication

**Version:** 1.0  
**Status:** Baseline  
**Verified:** Yes  
**Source:** `src/calibration/h3_characterize.py`

---

## Overview

This specification describes the SMC3 serial communication subsystem of the v0.4.1 characterization tool. It covers port configuration, baud rates, timeouts, and port ownership.

---

## Port Configuration

### H3 Motor Controller Port

| Parameter | Value | Source |
|-----------|-------|--------|
| Default path | None (requires explicit value) | Line 462 |
| Baud rate | 500000 (500 kbps) | Line 36, 572 |
| Read timeout | 0.5 seconds (passed to serial constructor) | Line 572 |
| Write timeout | 0.5 seconds (passed to serial constructor) | Line 572 |

### WT901C Sensor Port

| Parameter | Value | Source |
|-----------|-------|--------|
| Default path | `/dev/ttyUSB0` | Line 463 |
| Baud rate | 9600 | Line 37, 582 |
| Read timeout | 0.1 seconds | Line 582 |

### Port Ownership

**Verified:** Two separate serial connections are used:

1. **H3 Port:** Motor commands and readback polling
2. **WT901C Port:** Sensor acquisition only

**Evidence:** Lines 572, 582-584

---

## Initialization Sequence

### Arduino USB Reset Delay

After opening the H3 serial port, a 2-second delay is inserted:

```python
h3 = factory(h3_port, SMC3_BAUD, timeout=0.5, write_timeout=0.5)
time.sleep(2.0)  # Arduino USB reset delay
h3.reset_input_buffer()
```

**Evidence:** Lines 572-574

**Purpose:** Accommodates Arduino USB enumeration delay after port opening.

---

## Serial Factory Pattern

The tool uses a factory pattern for serial port creation:

```python
factory = serial_factory or serial.Serial
h3 = factory(h3_port, SMC3_BAUD, timeout=0.5, write_timeout=0.5)
wt = factory(args.wt_port, WT_BAUD, timeout=0.1)
```

**Evidence:** Lines 554, 572, 582

**Purpose:** Allows test injection of mock serial ports.

---

## Input Buffer Reset

After opening the H3 port, the input buffer is reset:

```python
h3.reset_input_buffer()
```

**Evidence:** Line 574

**Purpose:** Clear any residual data from previous connections.

---

## Dependencies

- `serial` (pyserial library) - imported with fallback to None
- Python standard library modules: argparse, csv, datetime, math, statistics, threading, time, collections, pathlib

**Evidence:** Lines 31-34, 21-29

---

## Behavioral Notes

### No Hardware Connection Assumption

The tool does not assume hardware is connected. Serial operations may fail if ports are unavailable.

### Port Defaults May Differ

Argparse defaults (lines 462-463) may differ from docstring (line 9). Actual defaults should be verified from argparse configuration.

---

## Verification Status

**Verified:** Yes - All behaviors confirmed in source code.

**Evidence:** Direct examination of `src/calibration/h3_characterize.py` lines 36-37, 554, 572, 582.

---

## Related Specifications

- SM-02: Motor Command Protocol
- SM-03: Readback Polling
- SM-04: WT901C Sensor Acquisition

---

**End of Specification SM-01**
