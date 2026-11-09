# Specification SM-07: Threading and Lifecycle

**Version:** 1.0  
**Status:** Baseline  
**Verified:** Yes  
**Source:** `src/calibration/h3_characterize.py`

---

## Overview

This specification describes the threading model and lifecycle management of the v0.4.1 characterization tool.

---

## Thread Model

### Main Thread

**Verified:** The main thread performs all synchronous operations:
- CLI argument parsing
- Serial port opening
- Motor command transmission
- Readback polling
- CSV file writing
- Summary printing

**Evidence:** Lines 460-687

### WT901CReader Thread

**Verified:** A single daemon thread handles WT901C sensor acquisition.

```python
self.thread = threading.Thread(target=self._run, name="wt901c", daemon=True)
```

**Evidence:** Line 309

---

## WT901CReader Lifecycle

### Initialization

```python
def __init__(self, ser):
    self.ser = ser
    self.stop_event = threading.Event()
    self.thread = None
    self.buffer = bytearray()
    self.latest = {}
    self.samples = deque()
    self.lock = threading.Lock()
    self.valid_packets = 0
    self.bad_checksums = 0
    self.sample_count = 0
```

**Evidence:** Lines 296-306

### start()

Creates and starts the daemon thread:

```python
def start(self):
    self.thread = threading.Thread(target=self._run, name="wt901c", daemon=True)
    self.thread.start()
```

**Evidence:** Lines 308-310

**Behavior:**
- Creates new thread with target `_run`
- Thread name: "wt901c"
- Daemon thread (exits when main thread exits)
- Thread begins executing `_run()` immediately

### stop()

Stops the thread with timeout:

```python
def stop(self):
    self.stop_event.set()
    if self.thread:
        self.thread.join(timeout=2.0)
```

**Evidence:** Lines 312-315

**Behavior:**
- Sets stop event to signal thread termination
- Joins thread with 2.0 second timeout
- Thread terminates cleanly when stop event is set

### _run()

Main thread loop:

```python
def _run(self):
    while not self.stop_event.is_set():
        try:
            data = self.ser.read(128)
            if not data:
                continue
            self.buffer.extend(data)
            self._parse_buffer()
        except serial.SerialTimeoutException:
            pass
```

**Evidence:** Lines 327-333

**Behavior:**
- Reads up to 128 bytes from serial port
- Accumulates data in buffer
- Parses complete WIT packets from buffer
- Handles timeout exceptions gracefully

---

## Sample Queue Operations

### discard_samples()

Clears the sample queue:

```python
def discard_samples(self):
    with self.lock:
        self.samples.clear()
```

**Evidence:** Lines 317-319

**Behavior:**
- Thread-safe (uses lock)
- Clears all queued samples

### pop_samples()

Returns queued samples:

```python
def pop_samples(self):
    with self.lock:
        result = list(self.samples)
        self.samples.clear()
        return result
```

**Evidence:** Lines 321-325

**Behavior:**
- Thread-safe (uses lock)
- Returns copy of all queued samples
- Clears queue after returning

---

## Thread Safety

### Lock Usage

```python
self.lock = threading.Lock()
```

**Evidence:** Line 303

### Protected Operations

All queue operations use the lock:

```python
with self.lock:
    self.latest[typ] = (now, x, y, z)
    self.valid_packets += 1
    if typ == 0x53:
        self.sample_count += 1
        self.samples.append((self.sample_count, now, dict(self.latest)))
```

**Evidence:** Lines 359-364

### Latest Data Dictionary

**Verified:** The `self.latest` dictionary accumulates all packet types:

```python
self.latest[typ] = (now, x, y, z)
```

**Evidence:** Line 360

**Types stored:**
- 0x51: ACCEL data
- 0x52: GYRO data
- 0x53: ANGLE data
- 0x54: MAG data

### Sample Queue

**Verified:** Only ANGLE (0x53) packets are queued:

```python
if typ == 0x53:
    self.sample_count += 1
    self.samples.append((self.sample_count, now, dict(self.latest)))
```

**Evidence:** Lines 362-364

---

## Context Managers

### TXLogger Context Manager

```python
def __enter__(self):
    self.file = self.filepath.open("x", newline="")
    self.writer = csv.writer(self.file)
    ...
    return self

def __exit__(self, exc_type, exc_val, exc_tb):
    if self.file:
        self.file.close()
    return False
```

**Evidence:** Lines 60-74

**Behavior:**
- Opens file on entry
- Closes file on exit
- Does not suppress exceptions (returns False)

### ReadbackPoller Context Manager

```python
def __enter__(self):
    self.log_file = self.filepath.open("x", newline="")
    self.writer = csv.writer(self.log_file)
    ...
    return self

def __exit__(self, exc_type, exc_val, exc_tb):
    if self.log_file:
        self.log_file.close()
    return False
```

**Evidence:** Lines 106-121

**Behavior:**
- Opens file on entry
- Closes file on exit
- Does not suppress exceptions (returns False)

---

## Error Handling

### WT901CReader Timeout

Serial read timeouts are handled gracefully:

```python
try:
    data = self.ser.read(128)
    ...
except serial.SerialTimeoutException:
    pass
```

**Evidence:** Lines 328-333

### ReadbackPoller Exception

Readback polling catches exceptions:

```python
try:
    written = self.ser.write(request)
    ...
except Exception as exc:
    error = f"{type(exc).__name__}: {exc}"
    status = "ERROR"
    ...
```

**Evidence:** Lines 158-163

---

## Verification Status

**Verified:** Yes - All behaviors confirmed in source code.

**Evidence:** Direct examination of `src/calibration/h3_characterize.py` lines 293-459, 308-315, 317-325, 359-364.

---

## Related Specifications

- SM-01: SMC3 Serial Communication
- SM-04: WT901C Sensor Acquisition
- SM-05: Logging and CSV Output

---

**End of Specification SM-07**
