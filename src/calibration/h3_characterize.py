#!/usr/bin/env python3
"""DOF Reality H3 / WT901C physical-motion characterization.

This tool deliberately bypasses the normal CommandHub latest-value-wins queue.
Every requested H3 position is transmitted explicitly so the resulting CSV
represents the positions the H3 was actually commanded to visit.

H3: 500000 baud, SMC3 frames [A/B/C high low]. Center = 512.
WT901C: read-only, /dev/ttyUSB0, 9600 baud, WIT binary packets.

No WT901C configuration commands are sent.

v0.4.1 corrections:
- --tx-log FILE: log all SMC3 transmissions
- --readback: enable SMC3 controller feedback polling
  - --readback-timeout: response timeout in seconds (default: 0.10)
  - --readback-interval: polling interval in seconds (default: 0.25)
  - --readback-motors: A, B, C, or combination
"""

import argparse
import csv
import datetime as dt
import math
import statistics
import threading
import time
from collections import deque
from pathlib import Path

try:
    import serial
except ImportError:
    serial = None

SMC3_BAUD = 500000
WT_BAUD = 9600
CENTER = 512
MIN_POS = 0
MAX_POS = 1023
FRAME_LEN = 11

# SMC3 read command bytes
READ_COMMANDS = {
    "A": bytes([91, 114, 100, 97, 93]),  # [rda]
    "B": bytes([91, 114, 100, 98, 93]),  # [rdb]
    "C": bytes([91, 114, 100, 99, 93]),  # [rdc]
}


class TXLogger:
    """CSV logger for every attempted SMC3 serial transmission."""

    def __init__(self, filepath, run_start):
        self.filepath = Path(filepath)
        self.run_start = run_start
        self.file = None
        self.writer = None

    def __enter__(self):
        # Exclusive creation prevents accidental overwrite and handles races.
        self.file = self.filepath.open("x", newline="")
        self.writer = csv.writer(self.file)
        self.writer.writerow([
            "timestamp", "elapsed_ms", "command_type", "motor", "position",
            "bytes_hex", "bytes_written", "expected", "status", "error"
        ])
        self.file.flush()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.file:
            self.file.close()
        return False

    def log(self, command_type, motor, position, command_bytes,
            written, expected, status=None, error=""):
        now_mono = time.monotonic()
        now = dt.datetime.now().astimezone().isoformat(timespec="milliseconds")
        if status is None:
            status = "OK" if written == expected else "SHORT"
        self.writer.writerow([
            now, f"{(now_mono - self.run_start) * 1000:.3f}", command_type,
            motor or "", "" if position is None else position,
            " ".join(f"{b:02X}" for b in command_bytes),
            "" if written is None else str(written), str(expected), status, error
        ])
        self.file.flush()


class ReadbackPoller:
    """Synchronous SMC3 readback; the main thread exclusively owns H3 serial I/O."""

    def __init__(self, ser, filepath, timeout=0.10, interval=0.25,
                 tx_logger=None, run_start=None):
        self.ser = ser
        self.filepath = Path(filepath)
        self.timeout = timeout
        self.interval = interval
        self.tx_logger = tx_logger
        self.run_start = run_start if run_start is not None else time.monotonic()
        self.log_file = None
        self.writer = None
        self.next_poll = 0.0

    def __enter__(self):
        self.log_file = self.filepath.open("x", newline="")
        self.writer = csv.writer(self.log_file)
        self.writer.writerow([
            "timestamp", "elapsed_ms", "motor", "requested_position",
            "request_hex", "response_hex", "response_len", "response_time_ms",
            "status", "error"
        ])
        self.log_file.flush()
        self.next_poll = time.monotonic()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.log_file:
            self.log_file.close()
        return False

    def poll_motor(self, motor, requested_position=None):
        request = READ_COMMANDS[motor]
        start = time.monotonic()
        written = None
        response = bytearray()
        error = ""
        status = "TIMEOUT"
        old_timeout = getattr(self.ser, "timeout", None)
        logged = False
        try:
            written = self.ser.write(request)
            if written != len(request):
                if self.tx_logger is not None:
                    self.tx_logger.log("READ", motor, None, request, written,
                                       len(request), "SHORT")
                    logged = True
                raise IOError(f"short readback request write: {written}/{len(request)}")
            self.ser.flush()
            if self.tx_logger is not None:
                self.tx_logger.log("READ", motor, requested_position, request, written,
                                   len(request), "OK")
                logged = True
            deadline = start + self.timeout
            # Temporarily bound each serial read by the remaining total deadline.
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                if hasattr(self.ser, "timeout"):
                    self.ser.timeout = remaining
                chunk = self.ser.read(1)
                if not chunk:
                    break
                response.extend(chunk)
            status = "OK" if response else "TIMEOUT"
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
            status = "ERROR"
            if self.tx_logger is not None and not logged:
                self.tx_logger.log("READ", motor, requested_position, request, written,
                                   len(request), "ERROR", error)
        finally:
            if hasattr(self.ser, "timeout"):
                self.ser.timeout = old_timeout

        finished = time.monotonic()
        now = dt.datetime.now().astimezone().isoformat(timespec="milliseconds")
        self.writer.writerow([
            now, f"{(finished - self.run_start) * 1000:.3f}", motor,
            "" if requested_position is None else requested_position,
            " ".join(f"{b:02X}" for b in request),
            " ".join(f"{b:02X}" for b in response), len(response),
            f"{(finished - start) * 1000:.3f}", status, error
        ])
        self.log_file.flush()
        return finished

    def poll_due(self, motors, positions):
        """Poll selected motors at the configured interval, without a worker thread."""
        now = time.monotonic()
        if now < self.next_poll:
            return
        for motor in motors:
            requested = positions["ABC".index(motor)]
            self.poll_motor(motor, requested)
        self.next_poll = time.monotonic() + self.interval

    def poll_now(self, motors, positions):
        for motor in motors:
            requested = positions["ABC".index(motor)]
            self.poll_motor(motor, requested)
        self.next_poll = time.monotonic() + self.interval


def smc3_frame(motor, position):
    if motor not in "ABC":
        raise ValueError(f"invalid motor: {motor!r}")
    position = max(MIN_POS, min(MAX_POS, int(position)))
    return bytes((91, ord(motor), (position >> 8) & 255, position & 255, 93))


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


def send_command(ser, command, tx_logger=None):
    if len(command) != 5 or command[0] != 91 or command[4] != 93:
        raise ValueError(f"invalid SMC3 command: {command!r}")
    command_type, motor, position = classify_command(command)
    written = None
    written = None
    logged = False
    try:
        written = ser.write(command)
        if written != len(command):
            if tx_logger is not None:
                tx_logger.log(command_type, motor, position, command, written,
                              len(command), "SHORT")
                logged = True
            raise IOError(f"short SMC3 write: {written}/{len(command)}")
        ser.flush()
    except Exception as exc:
        if tx_logger is not None and not logged:
            tx_logger.log(command_type, motor, position, command, written,
                          len(command), "ERROR", f"{type(exc).__name__}: {exc}")
        raise
    if tx_logger is not None:
        tx_logger.log(command_type, motor, position, command, written, len(command), "OK")


def send_motor(ser, motor, position, tx_logger=None):
    send_command(ser, smc3_frame(motor, position), tx_logger)


def send_all(ser, a, b, c, tx_logger=None):
    send_motor(ser, "A", a, tx_logger)
    send_motor(ser, "B", b, tx_logger)
    send_motor(ser, "C", c, tx_logger)


def request_version(ser, tx_logger=None):
    ser.reset_input_buffer()
    send_command(ser, b"[ver]", tx_logger)
    response = ser.read(5)
    if len(response) == 5 and response[0] == 91 and response[1] == ord("v"):
        value = (response[2] << 8) | response[3]
        print(f"SMC3 version: {value / 100:.2f}  raw={response!r}")
    else:
        print(f"SMC3 version response: {response!r}")


def signed16(lo, hi):
    value = lo | (hi << 8)
    return value - 65536 if value & 0x8000 else value


def decode_wit(frame):
    if len(frame) != FRAME_LEN or frame[0] != 0x55:
        return None
    if (sum(frame[:10]) & 0xFF) != frame[10]:
        return "BAD_CHECKSUM"

    typ = frame[1]
    x = signed16(frame[2], frame[3])
    y = signed16(frame[4], frame[5])
    z = signed16(frame[6], frame[7])

    if typ == 0x51:
        scale = 1.0 / 2048.0
    elif typ == 0x52:
        scale = 1.0 / 16.384
    elif typ == 0x53:
        scale = 180.0 / 32768.0
    elif typ == 0x54:
        scale = 1.0
    else:
        return None

    return typ, x * scale, y * scale, z * scale


class WT901CReader:
    """Read-only WIT parser. One queued sample is produced per ANGLE packet."""

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

    def start(self):
        self.thread = threading.Thread(target=self._run, name="wt901c", daemon=True)
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=2.0)

    def discard_samples(self):
        with self.lock:
            self.samples.clear()

    def pop_samples(self):
        with self.lock:
            result = list(self.samples)
            self.samples.clear()
            return result

    def _run(self):
        while not self.stop_event.is_set():
            data = self.ser.read(128)
            if not data:
                continue
            self.buffer.extend(data)
            self._parse_buffer()

    def _parse_buffer(self):
        while len(self.buffer) >= FRAME_LEN:
            try:
                start = self.buffer.index(0x55)
            except ValueError:
                self.buffer.clear()
                return
            if start:
                del self.buffer[:start]
            if len(self.buffer) < FRAME_LEN:
                return

            frame = bytes(self.buffer[:FRAME_LEN])
            decoded = decode_wit(frame)
            if decoded == "BAD_CHECKSUM":
                self.bad_checksums += 1
                del self.buffer[0]
                continue
            del self.buffer[:FRAME_LEN]
            if decoded is None:
                continue

            typ, x, y, z = decoded
            now = time.monotonic()
            with self.lock:
                self.latest[typ] = (now, x, y, z)
                self.valid_packets += 1
                if typ == 0x53:
                    self.sample_count += 1
                    self.samples.append((self.sample_count, now, dict(self.latest)))


CSV_FIELDS = [
    "timestamp", "elapsed_s", "phase", "motor", "sweep_direction", "offset",
    "A", "B", "C", "sample_index",
    "roll_deg", "pitch_deg", "yaw_deg",
    "accel_x_g", "accel_y_g", "accel_z_g",
    "gyro_x_dps", "gyro_y_dps", "gyro_z_dps",
    "mag_x", "mag_y", "mag_z",
]


def csv_row(run_start, phase, motor, direction, offset, positions, sample):
    index, timestamp, data = sample
    angle = data.get(0x53, (None, math.nan, math.nan, math.nan))
    accel = data.get(0x51, (None, math.nan, math.nan, math.nan))
    gyro = data.get(0x52, (None, math.nan, math.nan, math.nan))
    mag = data.get(0x54, (None, math.nan, math.nan, math.nan))

    return {
        "timestamp": dt.datetime.now().astimezone().isoformat(timespec="milliseconds"),
        "elapsed_s": f"{timestamp - run_start:.6f}",
        "phase": phase,
        "motor": motor,
        "sweep_direction": direction,
        "offset": offset,
        "A": positions[0], "B": positions[1], "C": positions[2],
        "sample_index": index,
        "roll_deg": f"{angle[1]:.6f}",
        "pitch_deg": f"{angle[2]:.6f}",
        "yaw_deg": f"{angle[3]:.6f}",
        "accel_x_g": f"{accel[1]:.6f}",
        "accel_y_g": f"{accel[2]:.6f}",
        "accel_z_g": f"{accel[3]:.6f}",
        "gyro_x_dps": f"{gyro[1]:.6f}",
        "gyro_y_dps": f"{gyro[2]:.6f}",
        "gyro_z_dps": f"{gyro[3]:.6f}",
        "mag_x": f"{mag[1]:.1f}",
        "mag_y": f"{mag[2]:.1f}",
        "mag_z": f"{mag[3]:.1f}",
    }


def positions_for(motor, offset):
    values = {"A": CENTER, "B": CENTER, "C": CENTER}
    values[motor] += offset
    if not all(MIN_POS <= v <= MAX_POS for v in values.values()):
        raise ValueError(f"position outside {MIN_POS}..{MAX_POS}: {values}")
    return values["A"], values["B"], values["C"]


def build_sweep(step, limit):
    """Build one continuous down-and-back, then up-and-back path.

    The path intentionally does not snap to center between the negative and
    positive sweeps.  Instead it reverses direction through center so that
    measurements at the same motor position can be compared by approach
    direction.

    Example (step=20, limit=100):
        -20, -40, -60, -80, -100,
        -80, -60, -40, -20, 0,
        +20, +40, +60, +80, +100,
        +80, +60, +40, +20, 0
    """
    negative_out = list(range(-step, -limit - 1, -step))
    if not negative_out or negative_out[-1] != -limit:
        negative_out.append(-limit)
    negative_out = sorted(set(negative_out), reverse=True)

    negative_return = list(range(-limit + step, 1, step))

    positive_out = list(range(step, limit + 1, step))
    if not positive_out or positive_out[-1] != limit:
        positive_out.append(limit)
    positive_out = sorted(set(positive_out))

    positive_return = list(range(limit - step, -1, -step))

    return (
        [("negative", v) for v in negative_out]
        + [("negative_return", v) for v in negative_return]
        + [("positive", v) for v in positive_out]
        + [("positive_return", v) for v in positive_return]
    )


def mean_sd(values):
    if not values:
        return math.nan, math.nan
    if len(values) == 1:
        return values[0], 0.0
    return statistics.mean(values), statistics.stdev(values)


def main(argv=None, serial_factory=None):
    parser = argparse.ArgumentParser(description="H3 physical motion vs WT901C characterization")
    parser.add_argument("--port", help="H3 SMC3 port, e.g. /dev/ttyACM0")
    parser.add_argument("--wt-port", default="/dev/ttyUSB0")
    parser.add_argument("--motors", default="ABC", help="A, B, C, or combination such as AB")
    parser.add_argument("--step", type=int, default=20)
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--settle", type=float, default=1.0)
    parser.add_argument("--measure", type=float, default=1.0)
    parser.add_argument("--center-settle", type=float, default=10.0,
                        help="seconds to settle at A=B=C=512 before reference capture")
    parser.add_argument("--center-measure", type=float, default=20.0,
                        help="seconds of WT901C reference capture at A=B=C=512")
    parser.add_argument("--output", default="h3_wt901c_characterization.csv")
    parser.add_argument("--no-version", action="store_true")
    parser.add_argument("--yes", action="store_true", help="skip physical-motion confirmation")
    parser.add_argument("--tx-log", metavar="FILE", help="log all SMC3 transmissions to CSV")
    parser.add_argument("--readback", action="store_true", help="enable SMC3 controller feedback polling")
    parser.add_argument("--readback-log", default="smc3_readback.csv", metavar="FILE",
                        help="readback CSV path (default: smc3_readback.csv)")
    parser.add_argument("--readback-timeout", type=float, default=0.10, metavar="SECONDS")
    parser.add_argument("--readback-interval", type=float, default=0.25, metavar="SECONDS")
    parser.add_argument("--readback-motors", default="ABC",
                        help="motors to poll: A, B, C, or combination")
    args = parser.parse_args(argv)

    if not args.motors or any(m not in "ABC" for m in args.motors):
        parser.error("--motors must contain only A, B, and C")
    args.motors = "".join(dict.fromkeys(args.motors))
    if args.step <= 0:
        parser.error("--step must be > 0")
    if not 0 < args.limit <= CENTER:
        parser.error("--limit must be between 1 and 512")
    if args.settle < 0 or args.center_settle < 0:
        parser.error("settle times must be >= 0")
    if args.measure <= 0 or args.center_measure <= 0:
        parser.error("measurement times must be > 0")
    if args.readback:
        if not 0.01 <= args.readback_timeout <= 5.0:
            parser.error("--readback-timeout must be between 0.01 and 5.0")
        if args.readback_interval <= 0:
            parser.error("--readback-interval must be > 0")
        if not args.readback_motors or any(m not in "ABC" for m in args.readback_motors):
            parser.error("--readback-motors must contain only A, B, and C")
        args.readback_motors = "".join(dict.fromkeys(args.readback_motors))
    if serial is None and serial_factory is None:
        raise RuntimeError("pyserial is required: pip install pyserial")

    output = Path(args.output)
    if output.exists():
        raise FileExistsError(f"Output file already exists: {output}. Choose a new --output filename.")
    log_paths = []
    if args.tx_log:
        log_paths.append(Path(args.tx_log))
    if args.readback:
        log_paths.append(Path(args.readback_log))
    for log_path in log_paths:
        if log_path.exists():
            raise FileExistsError(f"Log file already exists: {log_path}. Choose another filename.")
    if len(set([output, *log_paths])) != 1 + len(log_paths):
        raise ValueError("Output and log files must have different paths")

    if args.port:
        h3_port = args.port
    else:
        devices = sorted(Path("/dev").glob("ttyACM*"))
        if not devices:
            devices = sorted(Path("/dev").glob("ttyUSB*"))
        if not devices:
            raise RuntimeError("No /dev/ttyACM* or /dev/ttyUSB* device found")
        h3_port = str(devices[0])

    print("\nDOF Reality H3 / WT901C Characterization v0.4.1")
    print("================================================")
    print(f"H3:       {h3_port} @ {SMC3_BAUD}")
    print(f"WT901C:   {args.wt_port} @ {WT_BAUD} (read-only)")
    print(f"Motors:   {args.motors}")
    print(f"Sweep:    +/-{args.limit}, step {args.step}, center {CENTER}")
    print(f"Sweep settle:    {args.settle:.2f} s")
    print(f"Sweep measure:   {args.measure:.2f} s")
    print(f"Center settle:   {args.center_settle:.2f} s")
    print(f"Center measure:  {args.center_measure:.2f} s")
    print(f"CSV:      {output}")
    if args.tx_log:
        print(f"SMC3 TX log: {args.tx_log}")
    if args.readback:
        print(f"SMC3 readback: {args.readback_log} (motors {args.readback_motors})")
    print("\nWARNING: the H3 will physically move. Verify clearance before starting.")
    if not args.yes:
        answer = input("Press Enter to start, or q then Enter to abort: ").strip().lower()
        if answer == "q":
            print("Aborted before opening serial ports.")
            return 0

    factory = serial_factory or serial.Serial
    h3 = wt = None
    reader = None
    writer_file = None
    tx_logger = None
    readback_poller = None
    run_start = time.monotonic()
    centered = False

    try:
        # Open logs before enabling/moving hardware. Exclusive creation avoids overwrite.
        if args.tx_log:
            tx_logger = TXLogger(args.tx_log, run_start)
            tx_logger.__enter__()
        if args.readback:
            # Open after H3 serial setup below, but before any readback requests.
            pass

        h3 = factory(h3_port, SMC3_BAUD, timeout=0.5, write_timeout=0.5)
        time.sleep(2.0)  # Arduino USB reset delay used by the known-good transport.
        h3.reset_input_buffer()
        if args.readback:
            readback_poller = ReadbackPoller(
                h3, args.readback_log, args.readback_timeout, args.readback_interval,
                tx_logger, run_start
            )
            readback_poller.__enter__()

        wt = factory(args.wt_port, WT_BAUD, timeout=0.1)
        reader = WT901CReader(wt)
        reader.start()

        if not args.no_version:
            request_version(h3, tx_logger)
        send_command(h3, b"[ena]", tx_logger)
        send_all(h3, CENTER, CENTER, CENTER, tx_logger)
        centered = True
        print("H3 centered. Initial settle...")
        time.sleep(args.settle)
        reader.discard_samples()

        writer_file = output.open("x", newline="")
        csv_writer = csv.DictWriter(writer_file, fieldnames=CSV_FIELDS)
        csv_writer.writeheader()
        writer_file.flush()

        center_positions = (CENTER, CENTER, CENTER)
        send_all(h3, *center_positions, tx_logger=tx_logger)
        print(f"\nCENTER REFERENCE: A=512 B=512 C=512\n  Settling for {args.center_settle:.2f} s...")
        time.sleep(args.center_settle)
        reader.discard_samples()

        print(f"  Measuring WT901C reference for {args.center_measure:.2f} s...")
        center_end = time.monotonic() + args.center_measure
        center_captured = []
        while time.monotonic() < center_end:
            time.sleep(0.01)
            samples = reader.pop_samples()
            for sample in samples:
                csv_writer.writerow(csv_row(run_start, "center_reference", "REF",
                                            "center_reference", 0, center_positions, sample))
                center_captured.append(sample)
            if samples:
                writer_file.flush()

        center_angles = [(s[2][0x53][1], s[2][0x53][2], s[2][0x53][3])
                         for s in center_captured if 0x53 in s[2]]
        if center_angles:
            r, rsd = mean_sd([v[0] for v in center_angles])
            p_mean, psd = mean_sd([v[1] for v in center_angles])
            y, ysd = mean_sd([v[2] for v in center_angles])
            print(f"  Center reference: Roll={r:+8.3f} +/- {rsd:.3f} deg  "
                  f"Pitch={p_mean:+8.3f} +/- {psd:.3f} deg  "
                  f"Yaw={y:+8.3f} +/- {ysd:.3f} deg  ({len(center_angles)} samples)")
        else:
            print("  Center reference: no WT901C ANGLE samples received")

        for motor in args.motors:
            print("\n" + "=" * 68)
            print(f"MOTOR {motor} CHARACTERIZATION")
            print("=" * 68)
            for direction, offset in build_sweep(args.step, args.limit):
                positions = positions_for(motor, offset)
                print(f"\n{motor} {direction:8s} offset={offset:+4d} "
                      f"A={positions[0]:4d} B={positions[1]:4d} C={positions[2]:4d}")
                send_all(h3, *positions, tx_logger=tx_logger)
                time.sleep(args.settle)
                reader.discard_samples()
                if readback_poller is not None:
                    readback_poller.poll_now(args.readback_motors, positions)

                end_time = time.monotonic() + args.measure
                captured = []
                while time.monotonic() < end_time:
                    if readback_poller is not None:
                        readback_poller.poll_due(args.readback_motors, positions)
                    time.sleep(0.01)
                    samples = reader.pop_samples()
                    for sample in samples:
                        csv_writer.writerow(csv_row(run_start, "sweep", motor,
                                                    direction, offset, positions, sample))
                        captured.append(sample)
                    if samples:
                        writer_file.flush()

                angle_values = [(s[2][0x53][1], s[2][0x53][2], s[2][0x53][3])
                                for s in captured if 0x53 in s[2]]
                if not angle_values:
                    print("  WT901C: no ANGLE samples received")
                else:
                    r, rsd = mean_sd([v[0] for v in angle_values])
                    p_mean, psd = mean_sd([v[1] for v in angle_values])
                    y, ysd = mean_sd([v[2] for v in angle_values])
                    print(f"  WT901C mean: Roll={r:+8.3f} +/- {rsd:.3f} deg  "
                          f"Pitch={p_mean:+8.3f} +/- {psd:.3f} deg  "
                          f"Yaw={y:+8.3f} +/- {ysd:.3f} deg  ({len(angle_values)} samples)")

        print("\nCharacterization complete. Returning H3 to center.")
        send_all(h3, CENTER, CENTER, CENTER, tx_logger)
        centered = True
        time.sleep(max(1.0, args.settle))
        print(f"CSV saved to: {output}")
        print(f"WT901C valid packets: {reader.valid_packets}")
        print(f"WT901C bad checksums/resyncs: {reader.bad_checksums}")
        if args.tx_log:
            print(f"SMC3 TX log saved to: {args.tx_log}")
        if args.readback:
            print(f"SMC3 readback log saved to: {args.readback_log}")
        return 0

    except KeyboardInterrupt:
        print("\nInterrupted. Returning H3 to center...")
        if h3 is not None:
            try:
                send_all(h3, CENTER, CENTER, CENTER, tx_logger)
                centered = True
                time.sleep(1.0)
                print("H3 returned to center.")
            except Exception as exc:
                print(f"Could not send center command: {exc}")
        return 130
    except Exception:
        # Best-effort recovery on unexpected failures as well as Ctrl-C.
        if h3 is not None:
            print("\nError during characterization. Attempting to return H3 to center...")
            try:
                send_all(h3, CENTER, CENTER, CENTER, tx_logger)
                time.sleep(1.0)
                print("H3 returned to center.")
            except Exception as center_exc:
                print(f"Could not send center command: {center_exc}")
        raise
    finally:
        if reader is not None:
            reader.stop()
        if readback_poller is not None:
            readback_poller.__exit__(None, None, None)
        if writer_file is not None:
            writer_file.close()
        if wt is not None:
            wt.close()
        if h3 is not None:
            h3.close()
        if tx_logger is not None:
            tx_logger.__exit__(None, None, None)


if __name__ == "__main__":
    raise SystemExit(main())
