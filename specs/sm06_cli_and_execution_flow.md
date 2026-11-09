# Specification SM-06: CLI and Execution Flow

**Version:** 1.0  
**Status:** Baseline  
**Verified:** Yes  
**Source:** `src/calibration/h3_characterize.py`

---

## Overview

This specification describes the command-line interface and execution flow of the v0.4.1 characterization tool.

---

## Command Line Interface

### Argument Parser

```python
parser = argparse.ArgumentParser(description="H3 physical motion vs WT901C characterization")
```

**Evidence:** Line 461

### Arguments

| Argument | Type | Default | Description | Source |
|----------|------|---------|-------------|--------|
| `--port` | string | /dev/ttyUSB0 | H3 SMC3 port | Line 462 |
| `--wt-port` | string | /dev/ttyUSB0 | WT901C port | Line 463 |
| `--motors` | string | ABC | Motors to characterize | Line 464 |
| `--step` | int | 20 | Position step size | Line 465 |
| `--limit` | int | 100 | Sweep limit | Line 466 |
| `--settle` | float | 1.0 | Settle time per position | Line 467 |
| `--measure` | float | 1.0 | Measurement time per position | Line 468 |
| `--center-settle` | float | 10.0 | Center settling time | Line 469-470 |
| `--center-measure` | float | 20.0 | Center reference measurement time | Line 471-472 |
| `--output` | string | h3_wt901c_characterization.csv | Output CSV filename | Line 473 |
| `--no-version` | flag | False | Skip version request | Line 474 |
| `--yes` | flag | False | Auto-confirm | Line 475 |
| `--tx-log` | string | - | Enable TX logging | Line 476 |
| `--readback` | flag | False | Enable readback polling | Line 477 |
| `--readback-timeout` | float | 0.10 | Readback timeout | Line 478 |
| `--readback-interval` | float | 0.25 | Readback interval | Line 479 |
| `--readback-motors` | string | - | Motors to poll | Line 480 |

**Evidence:** Lines 461-480

---

## Execution Sequence

### Initialization (Lines 460-502)

1. Parse command line arguments
2. Validate arguments:
   - `step >= 1`
   - `limit >= step`
   - `motors` must be valid subset of "ABC"
   - Readback timeouts and intervals must be positive
3. Open TX log (if `--tx-log` specified)
4. Open H3 serial port

**Evidence:** Lines 461-505

### Hardware Setup (Lines 503-524)

1. Sleep 2.0 seconds (Arduino USB reset delay)
2. Reset H3 input buffer
3. Open readback log (if `--readback` specified)
4. Open WT901C serial port
5. Start WT901CReader daemon thread
6. Request H3 version (if not `--no-version`)
7. Send enable command

**Evidence:** Lines 503-524

### Center Reference (Lines 525-557)

1. Move to center (512, 512, 512)
2. Set centered flag
3. Print "H3 centered. Initial settle..."
4. Sleep for `--settle` seconds
5. Discard initial samples
6. Move to center again
7. Print center reference message
8. Sleep for `--center-settle` seconds
9. Measure for `--center-measure` seconds
10. Capture samples and log to CSV
11. Print center reference statistics

**Evidence:** Lines 543-557

### Sweep Execution (Lines 558-668)

For each motor in `--motors`:
1. Print motor characterization header
2. For each direction (negative, then positive):
   a. For each offset from `--step` to `--limit`:
      - Calculate positions for all motors
      - Print position information
      - Send positions to H3
      - Sleep for `--settle` seconds
      - Pop and log samples
      - Poll readback (if enabled)
   - Print completion message

**Evidence:** Lines 586-668

### Final Reference (Lines 669-678)

1. Move to center (512, 512, 512)
2. Print final reference message
3. Sleep for `--center-settle` seconds
4. Measure for `--center-measure` seconds
5. Capture samples and log to CSV
6. Print final reference statistics

**Evidence:** Lines 669-678

### Cleanup (Lines 679-687)

1. Return to center (512, 512, 512)
2. Sleep for `--settle` seconds
3. Print completion message
4. Print output CSV location
5. Print WT901C statistics

**Evidence:** Lines 679-687

---

## Context Manager Usage

### TXLogger

```python
if args.tx_log:
    tx_logger = TXLogger(args.tx_log, run_start)
    tx_logger.__enter__()
    # ... use logger ...
    tx_logger.__exit__()
```

**Evidence:** Lines 566-568, 650

### ReadbackPoller

```python
if args.readback:
    readback_poller = ReadbackPoller(...)
    readback_poller.__enter__()
    # ... use poller ...
    readback_poller.__exit__()
```

**Evidence:** Lines 576-580, 653

---

## Output CSV Generation

### Main CSV Writer

```python
writer_file = output.open("x", newline="")
csv_writer = csv.DictWriter(writer_file, fieldnames=CSV_FIELDS)
csv_writer.writeheader()
```

**Evidence:** Lines 595-598

### Row Generation

```python
csv_row(run_start, phase, motor, direction, offset, positions, sample)
```

**Evidence:** Lines 613-614, 652-653, 674-675

---

## Summary Output

### WT901C Statistics

```python
print(f"WT901C valid packets: {reader.valid_packets}")
print(f"WT901C bad checksums/resyncs: {reader.bad_checksums}")
```

**Evidence:** Lines 681-682

---

## Verification Status

**Verified:** Yes - All behaviors confirmed in source code.

**Evidence:** Direct examination of `src/calibration/h3_characterize.py` lines 460-687.

---

## Related Specifications

- SM-01: SMC3 Serial Communication
- SM-02: Motor Command Protocol
- SM-03: Readback Polling
- SM-04: WT901C Sensor Acquisition
- SM-05: Logging and CSV Output
- SM-07: Threading and Lifecycle

---

**End of Specification SM-06**
