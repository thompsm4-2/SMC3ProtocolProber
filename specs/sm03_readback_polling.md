# Specification SM-03: Readback Polling

**Version:** 1.0  
**Status:** Baseline  
**Verified:** Yes  
**Source:** `src/calibration/h3_characterize.py`

---

## Overview

This specification describes the readback polling subsystem of the v0.4.1 characterization tool. It covers polling behavior, timing, and logging.

---

## Architecture

### Synchronous Polling

**Verified:** Readback polling is synchronous - no separate thread.

```python
class ReadbackPoller:
    """Synchronous SMC3 readback; the main thread exclusively owns H3 serial I/O."""
```

**Evidence:** Line 92

### Serial Ownership

**Verified:** The main thread exclusively owns H3 serial I/O:

- Motor commands: H3 serial port
- Readback polling: Same H3 serial port
- WT901C: Separate serial port

**Evidence:** Line 92, Lines 572-584

---

## Configuration

### Default Values

| Parameter | Default | Source |
|-----------|---------|--------|
| Timeout | 0.10 seconds | Line 94, 498 |
| Interval | 0.25 seconds | Line 94, 499 |

**Evidence:** Lines 94-95, 498-499

### Command Line Options

- `--readback-timeout`: Response timeout in seconds (default: 0.10)
- `--readback-interval`: Polling interval in seconds (default: 0.25)
- `--readback-motors`: Motors to poll (A, B, C, or combination)

**Evidence:** Lines 498-499, 533-538

---

## Polling Behavior

### poll_motor()

Polls a single motor:

1. Send readback request (`[rda]`, `[rdb]`, or `[rdc]`)
2. Read response within timeout
3. Log request and response bytes

```python
def poll_motor(self, motor, requested_position=None):
    request = READ_COMMANDS[motor]
    start = time.monotonic()
    written = None
    response = bytearray()
    error = ""
    status = "TIMEOUT"
    ...
    written = self.ser.write(request)
    ...
    deadline = start + self.timeout
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        chunk = self.ser.read(1)
        if not chunk:
            break
        response.extend(chunk)
    status = "OK" if response else "TIMEOUT"
```

**Evidence:** Lines 123-157

### poll_due()

Polls selected motors at configured interval:

```python
def poll_due(self, motors, positions):
    now = time.monotonic()
    if now < self.next_poll:
        return
    for motor in motors:
        requested = positions["ABC".index(motor)]
        self.poll_motor(motor, requested)
    self.next_poll = time.monotonic() + self.interval
```

**Evidence:** Lines 180-188

### poll_now()

Polls all motors immediately:

```python
def poll_now(self, motors, positions):
    for motor in motors:
        requested = positions["ABC".index(motor)]
        self.poll_motor(motor, requested)
    self.next_poll = time.monotonic() + self.interval
```

**Evidence:** Lines 190-194

---

## Logging

### CSV Schema

```csv
timestamp,elapsed_ms,motor,requested_position,request_hex,response_hex,response_len,response_time_ms,status,error
```

| Column | Description |
|--------|-------------|
| timestamp | Wall clock time (ISO format) |
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

### Timestamp Calculation

```python
now = dt.datetime.now().astimezone().isoformat(timespec="milliseconds")
elapsed_ms = f"{(finished - self.run_start) * 1000:.3f}"
```

**Evidence:** Lines 169-171

---

## Response Handling

### No Position Extraction

**Verified:** The tool does NOT extract position from readback responses.

```python
response_hex = " ".join(f"{b:02X}" for b in response)
```

**Evidence:** Lines 173-174

### Limitation

**Unresolved:** The actual format of readback responses is not decoded. Raw bytes are logged only.

**Evidence:** Line 174

---

## Error Handling

### Timeout Handling

Readback polling uses a deadline-based timeout:

```python
deadline = start + self.timeout
while True:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        break
    chunk = self.ser.read(1)
    if not chunk:
        break
```

**Evidence:** Lines 145-156

### Status Reporting

| Status | Condition |
|--------|-----------|
| OK | Response received |
| TIMEOUT | No response within timeout |
| ERROR | Exception occurred |

**Evidence:** Lines 157, 158-160

---

## Verification Status

**Verified:** Yes - All behaviors confirmed in source code.

**Evidence:** Direct examination of `src/calibration/h3_characterize.py` lines 91-195.

---

## Related Specifications

- SM-01: SMC3 Serial Communication
- SM-02: Motor Command Protocol
- SM-05: Logging and CSV Output

---

**End of Specification SM-03**
