# Hardware Reference

## DOF Reality H3

Three-motor platform with motor identifiers A, B, and C. Motors A/B are mechanically coupled in the pitch/roll arrangement. Motor C has a distinct mechanical contribution; its actual axis coupling must be measured rather than assumed.

Known center command: 512. Known command range used in this project: 0–1023.

## SMC3 controller

Known observations:
- Arduino-based SMC3 controller.
- Firmware observed: `Arduino SMC3 ver 23.07`.
- Windows SMC3 Utility identified model `SH3_M3_b-D1`.
- Prior Windows COM port: COM4.
- Linux H3 serial device observed: `/dev/ttyACM0`.
- Baud rate used in the project: 500000.
- Device paths must be confirmed at each session.

### Five-byte motor frame

Format: `[` + motor letter + position high byte + position low byte + `]`.

```python
def smc3_frame(motor, position):
    position = max(0, min(1023, int(position)))
    return bytes((
        91, ord(motor),
        (position >> 8) & 255,
        position & 255,
        93
    ))
```

Examples:
- A=512: `5B 41 02 00 5D`
- A=510: `5B 41 01 FE 5D`
- Enable `[ena]`: `5B 65 6E 61 5D`
- Version `[ver]`: `5B 76 65 72 5D`
- Read requests: `[rda]`, `[rdb]`, `[rdc]`

The response format and semantics of the read requests are not established by the current TX log. The log shows transmitted requests, not received response bytes.

## Witmotion WT901C

- Model: WT901C RS232.
- USB serial adapter observed: CH341.
- Linux device observed: `/dev/ttyUSB0`.
- Baud rate: 9600.
- Sensor mounted on H3 and previously used by SRS for motion compensation.

Known WIT packet structure:
- 11 bytes, synchronization byte `0x55`.
- `0x51`: acceleration.
- `0x52`: angular velocity.
- `0x53`: angle.
- `0x54`: magnetometer.
- Checksum: sum of first 10 bytes modulo 256.
- Signed little-endian values.

Previously used scales:
- Acceleration: 1/2048 g.
- Angular velocity: 1/16.384 degrees/second.
- Angle: 180/32768 degrees.
- Magnetometer: raw values.

Verify the sensor configuration, packet parser, mounting alignment, and calibration before treating these values as definitive.
