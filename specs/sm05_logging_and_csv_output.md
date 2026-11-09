# Specification SM-05: Logging and CSV Output

**Version:** 1.0  
**Status:** Baseline  
**Verified:** Yes  
**Source:** `src/calibration/h3_characterize.py`

---

## Overview

This specification describes the logging and CSV output subsystem of the v0.4.1 characterization tool. It covers TX logging, readback logging, and main output CSV generation.

---

## TX Logger

### Purpose

Logs all SMC3 serial transmissions to a CSV file.

### CSV Schema

```csv
timestamp,elapsed_ms,command_type,motor,position,bytes_hex,bytes_written,expected,status,error
```

| Column | Description |
|--------|-------------|
| timestamp | Wall clock time (ISO format with milliseconds) |
| elapsed_ms | Time since run_start (milliseconds) |
| command_type | "VERSION", "ENABLE", "POSITION", "READ", or "UNKNOWN" |
| motor | Motor letter (A, B, C) or empty |
| position | Position value or empty |
| bytes_hex | Hex representation of transmitted bytes |
| bytes_written | Number of bytes written |
| expected | Expected number of bytes |
| status | "OK", "SHORT", or "ERROR" |
| error | Error message (if any) |

**Evidence:** Lines 64-67, 82-87

### File Creation

**Verified:** Uses exclusive creation mode ("x"):

```python
self.file = self.filepath.open("x", newline="")
```

**Evidence:** Line 62

**Behavior:**
- Creates file if does not exist
- Raises `FileExistsError` if file exists (does not truncate existing file)
- Creates parent directories if needed

**Evidence:** Line 62

### Timestamp Handling

```python
now = dt.datetime.now().astimezone().isoformat(timespec="milliseconds")
elapsed = f"{(now_mono - self.run_start) * 1000:.3f}"
```

**Evidence:** Lines 79-80

---

## Readback Logger

### Purpose

Logs SMC3 readback polling responses to a CSV file.

### CSV Schema

```csv
timestamp,elapsed_ms,motor,requested_position,request_hex,response_hex,response_len,response_time_ms,status,error
```

| Column | Description |
|--------|-------------|
| timestamp | Wall clock time (ISO format with milliseconds) |
| elapsed_ms | Time since run_start (milliseconds) |
| motor | Motor polled (A, B, or C) |
| requested_position | Position that was requested |
| request_hex | Hex representation of request bytes |
| response_hex | Hex representation of response bytes |
| response_len | Length of response in bytes |
| response_time_ms | Time to receive response (milliseconds) |
| status | "OK", "TIMEOUT", or "ERROR" |
| error | Error message (if any) |

**Evidence:** Lines 109-113, 170-176

### File Creation

**Verified:** Uses exclusive creation mode ("x"):

```python
self.log_file = self.filepath.open("x", newline="")
```

**Evidence:** Line 107

**Behavior:**
- Creates file if does not exist
- Raises `FileExistsError` if file exists (does not truncate existing file)
- Creates parent directories if needed

### Timestamp Handling

```python
now = dt.datetime.now().astimezone().isoformat(timespec="milliseconds")
elapsed_ms = f"{(finished - self.run_start) * 1000:.3f}"
```

**Evidence:** Lines 169-171

---

## Main Output CSV

### Purpose

Generates the main characterization output CSV file.

### CSV Schema

```csv
timestamp,elapsed_s,phase,motor,sweep_direction,offset,A,B,C,sample_index,roll_deg,pitch_deg,yaw_deg,accel_x_g,accel_y_g,accel_z_g,gyro_x_dps,gyro_y_dps,gyro_z_dps,mag_x,mag_y,mag_z
```

| Column | Description |
|--------|-------------|
| timestamp | Wall clock time (ISO format with milliseconds) |
| elapsed_s | Time since run_start (seconds) |
| phase | "center_reference", "sweep", or "final_reference" |
| motor | Motor being characterized (A, B, or C) |
| sweep_direction | "negative" or "positive" |
| offset | Position offset from center |
| A, B, C | Motor positions commanded |
| sample_index | Sample index within phase |
| roll_deg, pitch_deg, yaw_deg | Angle sensor values (degrees) |
| accel_x_g, accel_y_g, accel_z_g | Accelerometer values (g) |
| gyro_x_dps, gyro_y_dps, gyro_z_dps | Gyroscope values (deg/s) |
| mag_x, mag_y, mag_z | Magnetometer values |

**Evidence:** Lines 367-374, 384-405

---

## File Creation Behavior

### Mode "x" (Exclusive Creation)

**Verified:** All CSV files use mode "x":

```python
self.file = self.filepath.open("x", newline="")
self.log_file = self.filepath.open("x", newline="")
writer_file = output.open("x", newline="")
```

**Evidence:** Lines 62, 107, 595

**Behavior:**
- Creates file if does not exist
- Raises `FileExistsError` if file exists (does not truncate existing file)
- Creates parent directories if needed

**Note:** Mode "x" (exclusive creation) fails if the target file already exists. It does not truncate an existing file.

**Evidence:** test_v04.py line 159 (test expects FileExistsError)

---

## Timestamp Synchronization

### No Synchronization

**Verified:** There is NO timestamp synchronization between:
- TX log timestamps
- Readback log timestamps
- Main output CSV timestamps

**Evidence:**
- TX log: Lines 79-83
- Readback log: Lines 169-175
- Main CSV: Line 385

### Timestamp Sources

| Log Type | Timestamp Source |
|----------|------------------|
| TX log | Wall clock (astimezone) + monotonic elapsed |
| Readback log | Wall clock (astimezone) + monotonic elapsed |
| Main CSV | Wall clock only (astimezone) |

**Evidence:** Lines 79-83, 169-175, 385

---

## CSV Writer Configuration

### Newline Handling

All CSV files use `newline=""` for cross-platform compatibility:

```python
self.file = self.filepath.open("x", newline="")
```

**Evidence:** Lines 62, 107, 595

### Field Names

Main CSV field names:

```python
CSV_FIELDS = [
    "timestamp", "elapsed_s", "phase", "motor", "sweep_direction", "offset",
    "A", "B", "C", "sample_index",
    "roll_deg", "pitch_deg", "yaw_deg",
    "accel_x_g", "accel_y_g", "accel_z_g",
    "gyro_x_dps", "gyro_y_dps", "gyro_z_dps",
    "mag_x", "mag_y", "mag_z",
]
```

**Evidence:** Lines 367-374

---

## Verification Status

**Verified:** Yes - All behaviors confirmed in source code.

**Evidence:** Direct examination of `src/calibration/h3_characterize.py` lines 60-88, 106-116, 367-405.

---

## Related Specifications

- SM-01: SMC3 Serial Communication
- SM-02: Motor Command Protocol
- SM-03: Readback Polling
- SM-04: WT901C Sensor Acquisition
- SM-06: CLI and Execution Flow

---

**End of Specification SM-05**
