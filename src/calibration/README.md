# DOF Reality H3 / WT901C Characterization v0.4

This is the first physical characterization tool for measuring actual H3 motion with the WT901C mounted on the platform.

Incremental update of v0.3. The existing continuous motor sweep is preserved. v0.3 adds a settled WT901C center-reference capture before any motor characterization. v0.4 adds optional SMC3 TX logging and controller feedback polling.

## Purpose

Measure the relationship between:

`SMC3 commanded motor position -> actual H3 attitude / acceleration measured by WT901C`

The tool intentionally does **not** use the normal CommandHub latest-value-wins queue. Every sweep position is explicitly transmitted so intermediate measurement points are not collapsed.

## Confirmed hardware settings

### H3 / SMC3

- Port: `/dev/ttyACM0`
- Baud: `500000`
- Center: `512`
- Motors: `A`, `B`, `C`
- Position range used by this tool: `0..1023`
- Frame: `[<motor><high><low>]`

The Arduino USB reset delay of 2 seconds is retained from the known-good H3 serial transport.

### WT901C

- Port: `/dev/ttyUSB0`
- Baud: `9600`
- 8N1
- Read-only; no configuration commands are sent
- WIT packets: `0x51` acceleration, `0x52` angular velocity, `0x53` angle, `0x54` magnetometer

The WT901C angle packet is treated as the sample marker. Each angle sample is written to the CSV together with the most recent acceleration, gyro, and magnetometer packets.

## Default sweep

For each selected motor, the other two motors remain at 512.

With `--step 20 --limit 100` the sequence is:

`512 -> 492 -> 472 -> 452 -> 432 -> 412 -> 512 -> 532 -> 552 -> 572 -> 592 -> 612 -> 512`

This gives both directions and returns to center between the negative and positive portions.

## Recommended first physical test

Start with only Motor A to minimize platform movement and runtime:

```bash
python h3_characterize.py --port /dev/ttyACM0 --wt-port /dev/ttyUSB0 --motors A --step 20 --limit 100 --settle 1 --measure 1
```

The program will ask for confirmation before opening the ports.

The output file defaults to:

```text
h3_wt901c_characterization.csv
```

The CSV contains one row for every WT901C angle sample captured during each measurement window, including commanded A/B/C positions and roll/pitch/yaw, acceleration, angular velocity, and magnetometer values.

## Useful options

- `--motors A` / `B` / `C` / `ABC`
- `--step 20`
- `--limit 100`
- `--settle 1`
- `--measure 1`
- `--output FILE.csv`
- `--no-version` skips the SMC3 `[ver]` request
- `--yes` skips the confirmation prompt (use only when appropriate)
- `--tx-log FILE` log SMC3 transmissions to CSV
- `--readback` enable SMC3 controller feedback polling
- `--readback-timeout SECONDS` readback response timeout (default: 0.10, min: 0.01, max: 5.0)
- `--readback-interval SECONDS` readback polling interval (default: 0.25)
- `--readback-motors ABC` motors to poll for readback (A, B, C, or combination)

## TX Log Format

When `--tx-log FILE` is specified, a CSV log file is created containing every SMC3 command successfully handed to `serial.write()`.

```csv
timestamp,elapsed_ms,command_type,motor,position,bytes_hex,bytes_written,expected,status
```

| Field | Description |
|-------|-------------|
| `timestamp` | ISO format timestamp with milliseconds (e.g., `2026-11-01T12:00:00.123456`) |
| `elapsed_ms` | Monotonic time since program start (milliseconds) |
| `command_type` | One of: `POSITION`, `ENABLE`, `VERSION`, `UNKNOWN` |
| `motor` | Motor identifier (A/B/C) or empty for non-motor commands |
| `position` | Requested position (integer) or empty |
| `bytes_hex` | Exact transmitted bytes in hex (e.g., `5B4102005D`) |
| `bytes_written` | Actual bytes accepted by `serial.write()` |
| `expected` | Expected bytes |
| `status` | `OK` for successful writes, `SHORT` for short writes, `ERROR` for exceptions |

**Important:** A successful write confirms that the serial stack accepted the bytes. It does NOT prove that the Arduino physically received or executed the command.

## Readback Log Format

When `--readback` is specified, a CSV log file (`smc3_readback.log`) is created containing SMC3 controller response data.

```csv
timestamp,elapsed_ms,motor,request_hex,response_hex,response_len,response_time_ms,status
```

| Field | Description |
|-------|-------------|
| `timestamp` | ISO format timestamp with milliseconds |
| `elapsed_ms` | Monotonic time since program start (milliseconds) |
| `motor` | Motor identifier (A/B/C) |
| `request_hex` | Exact request bytes in hex |
| `response_hex` | Raw response bytes in hex (empty if timeout) |
| `response_len` | Number of bytes received |
| `response_time_ms` | Time from send to receive completion (milliseconds) |
| `status` | `OK` for successful response, `TIMEOUT` for no response |

## Readback Polling

The `--readback` option enables polling of SMC3 controller data using the read commands:

- `[rda]` — request Motor A data
- `[rdb]` — request Motor B data
- `[rdc]` — request Motor C data

Each read command is 5 bytes. The tool captures raw response bytes without decoding, as the response format has not yet been established.

Polling occurs at regular intervals during measurement windows, after the motor has settled at its new position. This allows correlation between:

1. Python's requested position
2. Bytes passed to the serial driver
3. Controller-reported motor data
4. WT901C measured orientation

## Safety / behavior

- The H3 physically moves through the requested range.
- Ctrl-C attempts to return all three motors to 512 before exiting.
- Normal completion also returns all three motors to 512.
- The WT901C is never configured or written to.

## Validation performed before physical use

- Python bytecode compilation: passed
- Module import: passed
- CLI `--help`: passed
- SMC3 frame encoding checks: passed
- WT901C packet decoding and checksum rejection: passed
- Sweep generation checks: passed
- Full fake-serial H3 + WT901C characterization run: passed
- Simulated H3 writes: `[ena]` plus explicit A/B/C frames for every commanded position
- TX logging: passed
- Readback polling: passed
- No physical H3 test was performed by this development environment

## Sweep sequence

The characterization sweep is continuous: center -> negative limit -> center -> positive limit -> center. The return legs pass through every intermediate position rather than snapping directly to center. This allows the same motor positions to be compared from opposite approach directions.

## New in v0.4

Added optional diagnostic features:

1. **SMC3 TX Logging**: Log all SMC3 transmissions with `--tx-log FILE`
2. **SMC3 Readback Polling**: Capture controller responses with `--readback`

These features enable investigation of whether Motor C's apparent reversal and return-position behavior originates in:
- The Python application
- Serial communication
- SMC3 controller
- Physical mechanism

## Known / Unknown about SMC3 Readback

### Known

- Read commands are exactly 5 bytes: `[rda]`, `[rdb]`, `[rdc]`
- Response format has not been established
- Raw responses are captured and logged
- Polling occurs at configurable intervals during measurement windows

### Unknown

- Response byte structure
- Whether responses contain motor position data
- Whether responses include timestamps
- Whether responses are formatted similarly to `[ver]` response

## Recommended run

For the next reference capture and characterization:

```bash
python h3_characterize.py \
  --port /dev/ttyACM0 \
  --wt-port /dev/ttyUSB0 \
  --motors ABC \
  --step 20 \
  --limit 100 \
  --settle 2 \
  --measure 1 \
  --center-settle 10 \
  --center-measure 20 \
  --output h3_wt901c_characterization_v0.4.csv
```

Use `--yes` to skip the physical-motion confirmation prompt.

To enable TX logging and readback polling:

```bash
python h3_characterize.py \
  --port /dev/ttyACM0 \
  --wt-port /dev/ttyUSB0 \
  --tx-log smc3_tx.log \
  --readback \
  --readback-motors ABC \
  --readback-timeout 0.10 \
  --readback-interval 0.25 \
  --motors C \
  --step 20 \
  --limit 100 \
  --settle 1 \
  --measure 1 \
  --yes
```

## Validation

The v0.4 source should be validated for:

- Python bytecode compilation
- module import
- CLI help and argument validation
- SMC3 frame encoding
- WT901C packet decoding/checksum handling
- continuous sweep generation
- fake-serial center-reference capture
- fake-serial sweep capture
- CSV header/phase labeling
- refusal to append to an incompatible existing CSV
- TX logging functionality
- Readback polling functionality

No physical H3/WT901C test is performed during development validation.

## Run CLI

* v0.4
python h3_characterize.py --help
python h3_characterize_v0.4.1.py \
  --port /dev/ttyACM0 \
  --wt-port /dev/ttyUSB0 \
  --motors C \
  --step 20 \
  --limit 100 \
  --settle 3 \
  --measure 2 \
  --center-settle 10 \
  --center-measure 20 \
  --output h3_motor_c_v041.csv \
  --tx-log h3_motor_c_tx_v041.csv \
  --readback \
  --readback-log h3_motor_c_readback_v041.csv \
  --readback-motors C \
  --readback-interval 0.25 \
  --readback-timeout 0.10
