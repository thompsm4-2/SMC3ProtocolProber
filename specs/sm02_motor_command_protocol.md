# Specification SM-02: Motor Command Protocol

**Version:** 1.0  
**Status:** Baseline  
**Verified:** Yes  
**Source:** `src/calibration/h3_characterize.py`

---

## Overview

This specification describes the SMC3 motor command protocol used by the v0.4.1 characterization tool. It covers frame format, command encoding, and response handling.

---

## Frame Format

### Structure

SMC3 commands are 5-byte frames in the format: `[<motor><high><low>]`

| Byte | Name | Value | Description |
|------|------|-------|-------------|
| 0 | Opening Bracket | 0x5B (91) | ASCII `[` |
| 1 | Motor Code | 65-67 | 'A'='A', 'B'='B', 'C'='C' |
| 2 | Position High | 0-255 | High byte of position |
| 3 | Position Low | 0-255 | Low byte of position |
| 4 | Closing Bracket | 0x5D (93) | ASCII `]` |

**Evidence:** Lines 197-201

### Frame Construction

```python
def smc3_frame(motor, position):
    if motor not in "ABC":
        raise ValueError(f"invalid motor: {motor!r}")
    position = max(MIN_POS, min(MAX_POS, int(position)))
    return bytes((91, ord(motor), (position >> 8) & 255, position & 255, 93))
```

**Evidence:** Lines 197-201

---

## Position Encoding

### Valid Range

| Parameter | Value | Source |
|-----------|-------|--------|
| Minimum position | 0 | Line 39 |
| Maximum position | 1023 | Line 40 |
| Center position | 512 | Line 38 |

**Evidence:** Lines 38-40, 199-200

### Bounds Checking

Positions are clamped to valid range:

```python
position = max(MIN_POS, min(MAX_POS, int(position)))
```

**Evidence:** Line 200

---

## Command Types

### Position Commands

Format: `[<motor><high><low>]`

Examples:
- Motor A, position 0: `b'[A\x00\x00]'`
- Motor A, position 512: `b'[A\x02\x80]'`
- Motor A, position 1023: `b'[A\x04\xff]'`

**Evidence:** Lines 197-201

### Readback Commands

Format: `[rda]`, `[rdb]`, `[rdc]` (lowercase)

| Motor | Command | Bytes |
|-------|---------|-------|
| A | `[rda]` | `bytes([91, 114, 100, 97, 93])` |
| B | `[rdb]` | `bytes([91, 114, 100, 98, 93])` |
| C | `[rdc]` | `bytes([91, 114, 100, 99, 93])` |

**Evidence:** Lines 44-48, 124

### Other Commands

The implementation supports additional commands:

| Command | Purpose |
|---------|---------|
| `[ver]` | Request firmware version |
| `[ena]` | Enable motor controller |

**Evidence:** Lines 205-208

---

## Response Handling

### Readback Response Logging

The tool logs readback responses but does NOT decode them:

```python
response_hex = " ".join(f"{b:02X}" for b in response)
```

**Evidence:** Lines 173-174

### Limitation

**Unresolved:** The actual format of readback responses is not decoded or documented. Raw bytes are logged only.

**Evidence:** Line 174

---

## Command Transmission

### send_command()

```python
def send_command(ser, command, tx_logger=None):
    if len(command) != 5 or command[0] != 91 or command[4] != 93:
        raise ValueError(f"invalid SMC3 command: {command!r}")
    command_type, motor, position = classify_command(command)
    ...
    return ser.write(command)
```

**Evidence:** Lines 217-221

### send_motor()

```python
def send_motor(ser, motor, position, tx_logger=None):
    command = smc3_frame(motor, position)
    return send_command(ser, command, tx_logger)
```

**Evidence:** Lines 242-250

### send_all()

```python
def send_all(ser, a, b, c, tx_logger=None):
    send_motor(ser, "A", a, tx_logger)
    send_motor(ser, "B", b, tx_logger)
    send_motor(ser, "C", c, tx_logger)
```

**Evidence:** Lines 246-250

---

## Bugs and Issues

### Bug: Redundant Assignment

Line 222 contains redundant code:

```python
written = None
written = None  # BUG: Redundant assignment
```

**Evidence:** Line 222

**Impact:** None - dead code only.

---

## Verification Status

**Verified:** Yes - All behaviors confirmed in source code.

**Evidence:** Direct examination of `src/calibration/h3_characterize.py` lines 44-48, 197-250.

---

## Related Specifications

- SM-01: SMC3 Serial Communication
- SM-03: Readback Polling
- SM-06: CLI and Execution Flow

---

**End of Specification SM-02**
