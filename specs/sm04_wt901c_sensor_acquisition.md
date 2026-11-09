# Specification SM-04: WT901C Sensor Acquisition

**Version:** 1.0  
**Status:** Baseline  
**Verified:** Yes  
**Source:** `src/calibration/h3_characterize.py`

---

## Overview

This specification describes the WT901C sensor acquisition subsystem of the v0.4.1 characterization tool. It covers WIT packet format, decoding, and sample queuing.

---

## Architecture

### Daemon Thread

**Verified:** WT901C sensor acquisition runs in a single daemon thread.

```python
class WT901CReader:
    """Read-only WIT parser. One queued sample is produced per ANGLE packet."""

    def start(self):
        self.thread = threading.Thread(target=self._run, name="wt901c", daemon=True)
        self.thread.start()
```

**Evidence:** Lines 293-294, 308-310

### Thread Name

Thread name: `"wt901c"`

**Evidence:** Line 309

---

## Configuration

### Serial Port

| Parameter | Value | Source |
|-----------|-------|--------|
| Default path | `/dev/ttyUSB0` | Line 463 |
| Baud rate | 9600 | Line 37, 582 |
| Read timeout | 0.1 seconds | Line 582 |

**Evidence:** Lines 37, 582

---

## WIT Packet Format

### Frame Structure

WIT packets are 11-byte frames:

| Byte | Name | Description |
|------|------|-------------|
| 0 | Start | 0x55 (SYNCH) |
| 1 | Type | Packet type identifier |
| 2-3 | X (low) | X value low byte |
| 4-5 | X (high) | X value high byte |
| 6-7 | Y (low) | Y value low byte |
| 8-9 | Y (high) | Y value high byte |
| 10 | Checksum | Sum of bytes 0-9 (mod 256) |

**Evidence:** Lines 269-272, 338-343

### Frame Validation

```python
def decode_wit(frame):
    if len(frame) != FRAME_LEN or frame[0] != 0x55:
        return None
    if (sum(frame[:10]) & 0xFF) != frame[10]:
        return "BAD_CHECKSUM"
    ...
```

**Evidence:** Lines 268-272

---

## Packet Types

### Type Identifiers

| Type | Hex | Name | Scale | Description |
|------|-----|------|-------|-------------|
| 0x51 | 0x51 | ACCEL | 1/2048 | Accelerometer (g) |
| 0x52 | 0x52 | GYRO | 1/16.384 | Gyroscope (deg/s) |
| 0x53 | 0x53 | ANGLE | 180/32768 | Angle (degrees) |
| 0x54 | 0x54 | MAG | 1.0 | Magnetometer |

**Evidence:** Lines 279-288

### Scaling Factors

```python
if typ == 0x51:
    scale = 1.0 / 2048.0
elif typ == 0x52:
    scale = 1.0 / 16.384
elif typ == 0x53:
    scale = 180.0 / 32768.0
elif typ == 0x54:
    scale = 1.0
```

**Evidence:** Lines 279-288

### Value Decoding

```python
x = signed16(frame[2], frame[3]) * scale
y = signed16(frame[4], frame[5]) * scale
z = signed16(frame[6], frame[7]) * scale
```

**Evidence:** Lines 275-277

---

## Sample Queuing

### Queue Behavior

**Verified:** Samples are queued only when ANGLE (0x53) packets are received.

```python
if typ == 0x53:
    self.sample_count += 1
    self.samples.append((self.sample_count, now, dict(self.latest)))
```

**Evidence:** Lines 362-364

### Latest Data Accumulation

**Verified:** All packet types are accumulated in `self.latest`:

```python
self.latest[typ] = (now, x, y, z)
```

**Evidence:** Line 360

### Sample Structure

Each queued sample contains:

```python
(sample_index, timestamp, {
    0x51: (timestamp, accel_x, accel_y, accel_z),
    0x52: (timestamp, gyro_x, gyro_y, gyro_z),
    0x53: (timestamp, angle_roll, angle_pitch, angle_yaw),
    0x54: (timestamp, mag_x, mag_y, mag_z),
})
```

**Evidence:** Lines 357-364

---

## Lifecycle Management

### start()

Starts the daemon thread:

```python
def start(self):
    self.thread = threading.Thread(target=self._run, name="wt901c", daemon=True)
    self.thread.start()
```

**Evidence:** Lines 308-310

### stop()

Stops the thread with timeout:

```python
def stop(self):
    self.stop_event.set()
    if self.thread:
        self.thread.join(timeout=2.0)
```

**Evidence:** Lines 312-315

### discard_samples()

Clears the sample queue:

```python
def discard_samples(self):
    with self.lock:
        self.samples.clear()
```

**Evidence:** Lines 317-319

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

---

## Thread Safety

### Lock Usage

The sample queue is protected by a lock:

```python
with self.lock:
    self.latest[typ] = (now, x, y, z)
    self.valid_packets += 1
    if typ == 0x53:
        self.sample_count += 1
        self.samples.append((self.sample_count, now, dict(self.latest)))
```

**Evidence:** Lines 359-364

### Lock Type

Uses `threading.Lock`:

```python
self.lock = threading.Lock()
```

**Evidence:** Line 303

---

## Tracking Statistics

### Counters

| Counter | Description |
|---------|-------------|
| valid_packets | Total valid packets received |
| bad_checksums | Packets with bad checksums |
| sample_count | ANGLE packets queued |

**Evidence:** Lines 304-306, 350, 362-363

---

## Usage in main()

### Start Sequence

```python
wt = factory(args.wt_port, WT_BAUD, timeout=0.1)
reader = WT901CReader(wt)
reader.start()
```

**Evidence:** Lines 582-584

### Discard Initial Samples

```python
reader.discard_samples()
```

**Evidence:** Line 593

### Capture Reference

```python
while time.monotonic() < center_end:
    time.sleep(0.01)
    samples = reader.pop_samples()
    for sample in samples:
        csv_writer.writerow(...)
```

**Evidence:** Lines 609-615

---

## Verification Status

**Verified:** Yes - All behaviors confirmed in source code.

**Evidence:** Direct examination of `src/calibration/h3_characterize.py` lines 268-459.

---

## Unresolved Questions

### UQ-04-01: Sampling Rate

The effective sampling rate is determined by the loop frequency and read timeout. The actual rate is not documented or configurable.

**Evidence:** Lines 327-333

---

## Related Specifications

- SM-01: SMC3 Serial Communication
- SM-05: Logging and CSV Output
- SM-07: Threading and Lifecycle

---

**End of Specification SM-04**
