
#!/usr/bin/env python3
"""
DOF Reality H3 - Incremental SMC3 Readback Diagnostic

For each selected motor:
    512 -> 612 in +1 increments
    612 -> 512 in -1 increments
    512 -> 412 in -1 increments
    412 -> 512 in +1 increments

Every individual position command is followed by a feedback readback.

IMPORTANT:
    Before opening the CSV or collecting measurements, the script:
      1. Enables all motors.
      2. Commands A, B and C to 512.
      3. Waits for the platform to settle.

The CSV records feedback and target readback separately.
The first command after each direction reversal is marked.

Requires:
    pyserial

Example:
    python smc3_incremental_readback.py \
        --port /dev/ttyACM0 \
        --motor A \
        --active \
        --csv smc3_motor_A_incremental.csv
"""

import argparse
import csv
import datetime
import sys
import time
from pathlib import Path

try:
    import serial
except ImportError:
    serial = None


BAUD = 500000
CENTER = 512
DELTA = 100

MOTORS = ("A", "B", "C")

ENABLE_COMMAND = b"[ena]"

FEEDBACK_COMMANDS = {
    "A": b"[rdA]",
    "B": b"[rdB]",
    "C": b"[rdC]",
}


CSV_FIELDS = [
    "timestamp",
    "elapsed_s",
    "sequence",
    "motor",
    "phase",
    "direction",
    "reversal",
    "step",
    "commanded_position",
    "position_command_hex",
    "feedback_command_hex",
    "feedback_response_hex",
    "framing_valid",
    "feedback_raw",
    "target_raw",
    "feedback_x4_candidate",
    "target_x4_candidate",
    "error",
]


def position_frame(motor, position):
    if motor not in MOTORS:
        raise ValueError(f"Invalid motor: {motor}")

    if not 0 <= position <= 1023:
        raise ValueError(f"Position outside SMC3 range: {position}")

    return bytes((
        0x5B,
        ord(motor),
        (position >> 8) & 0xFF,
        position & 0xFF,
        0x5D,
    ))


def write_command(port, command):
    written = port.write(command)

    if written != len(command):
        raise IOError(
            f"Short serial write: {written}/{len(command)} bytes"
        )

    port.flush()


def read_response(port, timeout):
    """
    Read one bracket-delimited SMC3 response.

    Expected response structure:
        [ identifier payload1 payload2 ]

    Returns the raw response bytes.
    """

    deadline = time.monotonic() + timeout
    response = bytearray()
    started = False

    while time.monotonic() < deadline:
        byte = port.read(1)

        if not byte:
            continue

        value = byte[0]

        if not started:
            if value == 0x5B:
                response.append(value)
                started = True
            continue

        response.append(value)

        if value == 0x5D:
            return bytes(response)

        if len(response) > 32:
            break

    return bytes(response)


def decode_feedback(response, motor):
    """
    Decode the five-byte feedback response.

    Expected:
        [ <motor> feedback target ]

    The raw payload bytes are retained. Multiplication by four
    is reported as a candidate scale, not an established fact.
    """

    if len(response) != 5:
        return None, None, False

    if response[0] != 0x5B or response[4] != 0x5D:
        return None, None, False

    if response[1] != ord(motor):
        return None, None, False

    feedback_raw = response[2]
    target_raw = response[3]

    return feedback_raw, target_raw, True


def query_feedback(port, motor, timeout):
    command = FEEDBACK_COMMANDS[motor]

    write_command(port, command)
    response = read_response(port, timeout)

    feedback, target, valid = decode_feedback(response, motor)

    return command, response, feedback, target, valid


def center_all_motors(port, settle):
    """
    Center all three motors before any measurement capture.
    """

    print("\nCentering all motors before measurement capture.")

    write_command(port, ENABLE_COMMAND)
    print("  Sent [ena]")

    time.sleep(0.1)

    for motor in MOTORS:
        command = position_frame(motor, CENTER)
        write_command(port, command)
        print(f"  Motor {motor}: commanded {CENTER}")

    print(f"Waiting {settle:.2f} seconds for platform to settle.")
    time.sleep(settle)

    print("Center commands completed.\n")


def capture_baseline(port, writer, start_time, timeout):
    """
    Capture feedback for all motors after the initial centering.
    """

    print("Capturing initial centered feedback baseline.")

    for motor in MOTORS:
        command, response, feedback, target, valid = query_feedback(
            port, motor, timeout
        )

        elapsed = time.monotonic() - start_time

        writer.writerow({
            "timestamp": datetime.datetime.now().isoformat(),
            "elapsed_s": f"{elapsed:.6f}",
            "sequence": 0,
            "motor": motor,
            "phase": "center_baseline",
            "direction": 0,
            "reversal": 0,
            "step": 0,
            "commanded_position": CENTER,
            "position_command_hex": "",
            "feedback_command_hex": command.hex(" ").upper(),
            "feedback_response_hex": response.hex(" ").upper(),
            "framing_valid": valid,
            "feedback_raw": feedback,
            "target_raw": target,
            "feedback_x4_candidate": (
                feedback * 4 if feedback is not None else ""
            ),
            "target_x4_candidate": (
                target * 4 if target is not None else ""
            ),
            "error": "",
        })

        print(
            f"  {motor}: feedback={feedback}, target={target}, "
            f"valid={valid}"
        )


def run_phase(
    port,
    writer,
    motor,
    phase,
    start_position,
    end_position,
    direction,
    reversal,
    sequence,
    start_time,
    timeout,
    interval,
):
    """
    Send one position command at a time and read feedback after
    every individual command.
    """

    position = start_position
    step_count = abs(end_position - start_position)

    print(
        f"\nMotor {motor}: {phase} "
        f"{start_position} -> {end_position}"
    )

    for step in range(1, step_count + 1):
        position += direction

        position_command = position_frame(motor, position)

        error = ""

        try:
            write_command(port, position_command)

            feedback_command, response, feedback, target, valid = (
                query_feedback(port, motor, timeout)
            )

            if not valid:
                error = "INVALID_OR_MISSING_FEEDBACK"

        except Exception as exc:
            feedback_command = FEEDBACK_COMMANDS[motor]
            response = b""
            feedback = None
            target = None
            valid = False
            error = str(exc)

        sequence += 1
        elapsed = time.monotonic() - start_time

        is_first_reversal_command = int(reversal and step == 1)

        writer.writerow({
            "timestamp": datetime.datetime.now().isoformat(),
            "elapsed_s": f"{elapsed:.6f}",
            "sequence": sequence,
            "motor": motor,
            "phase": phase,
            "direction": direction,
            "reversal": is_first_reversal_command,
            "step": step,
            "commanded_position": position,
            "position_command_hex": (
                position_command.hex(" ").upper()
            ),
            "feedback_command_hex": (
                feedback_command.hex(" ").upper()
            ),
            "feedback_response_hex": (
                response.hex(" ").upper()
            ),
            "framing_valid": valid,
            "feedback_raw": (
                feedback if feedback is not None else ""
            ),
            "target_raw": (
                target if target is not None else ""
            ),
            "feedback_x4_candidate": (
                feedback * 4 if feedback is not None else ""
            ),
            "target_x4_candidate": (
                target * 4 if target is not None else ""
            ),
            "error": error,
        })

        if step == 1 or step == step_count or step % 10 == 0:
            marker = " REVERSAL" if is_first_reversal_command else ""

            print(
                f"  {step:3d}/{step_count}: "
                f"command={position:4d} "
                f"feedback={str(feedback):>4s} "
                f"target={str(target):>4s} "
                f"valid={valid}{marker}"
            )

        if error:
            print(f"  ERROR: {error}")
            raise RuntimeError(
                f"Stopping test after readback/write error on motor {motor}"
            )

        if interval > 0:
            time.sleep(interval)

    return sequence


def run_motor(port, writer, motor, args, sequence, start_time):
    """
    Run the four incremental phases for one motor.
    """

    sequence = run_phase(
        port, writer, motor,
        "positive_excursion",
        CENTER, CENTER + DELTA,
        direction=1,
        reversal=False,
        sequence=sequence,
        start_time=start_time,
        timeout=args.read_timeout,
        interval=args.interval,
    )

    sequence = run_phase(
        port, writer, motor,
        "return_from_positive",
        CENTER + DELTA, CENTER,
        direction=-1,
        reversal=True,
        sequence=sequence,
        start_time=start_time,
        timeout=args.read_timeout,
        interval=args.interval,
    )

    sequence = run_phase(
        port, writer, motor,
        "negative_excursion",
        CENTER, CENTER - DELTA,
        direction=-1,
        reversal=True,
        sequence=sequence,
        start_time=start_time,
        timeout=args.read_timeout,
        interval=args.interval,
    )

    sequence = run_phase(
        port, writer, motor,
        "return_from_negative",
        CENTER - DELTA, CENTER,
        direction=1,
        reversal=True,
        sequence=sequence,
        start_time=start_time,
        timeout=args.read_timeout,
        interval=args.interval,
    )

    return sequence


def parse_args():
    parser = argparse.ArgumentParser(
        description="Incremental SMC3 feedback/readback diagnostic"
    )

    parser.add_argument(
        "--port",
        required=True,
        help="SMC3 serial port, e.g. /dev/ttyACM0",
    )

    parser.add_argument(
        "--motor",
        required=True,
        choices=["A", "B", "C", "ALL"],
        help="Motor to test, or ALL for A, B and C",
    )

    parser.add_argument(
        "--active",
        action="store_true",
        help="Required confirmation before sending motor commands",
    )

    parser.add_argument(
        "--delta",
        type=int,
        default=DELTA,
        help="Excursion from center; minimum 100 counts",
    )

    parser.add_argument(
        "--settle",
        type=float,
        default=5.0,
        help="Seconds to wait after initial centering",
    )

    parser.add_argument(
        "--interval",
        type=float,
        default=0.05,
        help="Delay between individual command/readback cycles",
    )

    parser.add_argument(
        "--read-timeout",
        type=float,
        default=0.25,
        help="Feedback response timeout in seconds",
    )

    parser.add_argument(
        "--csv",
        default="smc3_incremental_readback.csv",
        help="Output CSV path",
    )

    args = parser.parse_args()

    if not args.active:
        parser.error("--active is required for motor movement")

    if args.delta < 100:
        parser.error("--delta must be at least 100")

    if args.delta > 511:
        parser.error("--delta cannot exceed 511 from center")

    if args.settle < 0 or args.interval < 0:
        parser.error("settle and interval cannot be negative")

    if args.read_timeout <= 0:
        parser.error("--read-timeout must be greater than zero")

    return args


def main():
    args = parse_args()

    if serial is None:
        print("ERROR: pyserial is required.", file=sys.stderr)
        return 1

    motors = MOTORS if args.motor == "ALL" else (args.motor,)

    port = None
    csv_file = None
    writer = None

    try:
        print("SMC3 incremental readback diagnostic")
        print("-------------------------------------")
        print(f"Port: {args.port}")
        print(f"Motors: {', '.join(motors)}")
        print(f"Excursion: +/-{args.delta}")
        print(f"CSV: {Path(args.csv).resolve()}")

        port = serial.Serial(
            args.port,
            BAUD,
            timeout=0.05,
            write_timeout=0.5,
        )

        # Allow the Arduino USB serial interface to initialize.
        time.sleep(2.0)
        port.reset_input_buffer()
        port.reset_output_buffer()

        # CRITICAL: Center all motors before opening the CSV or
        # collecting any measurements.
        center_all_motors(port, args.settle)

        # Measurement capture starts only after centering.
        csv_file = open(
            args.csv,
            "w",
            newline="",
            encoding="utf-8",
        )

        writer = csv.DictWriter(
            csv_file,
            fieldnames=CSV_FIELDS,
        )
        writer.writeheader()
        csv_file.flush()

        start_time = time.monotonic()

        capture_baseline(
            port,
            writer,
            start_time,
            args.read_timeout,
        )
        csv_file.flush()

        sequence = 0

        for motor in motors:
            sequence = run_motor(
                port,
                writer,
                motor,
                args,
                sequence,
                start_time,
            )
            csv_file.flush()

        print("\nIncremental diagnostic completed.")

    except KeyboardInterrupt:
        print("\nInterrupted by user.")

    except Exception as exc:
        print(f"\nERROR: {exc}", file=sys.stderr)
        return 1

    finally:
        if port is not None and port.is_open:
            print("\nReturning all motors to 512/512/512.")

            try:
                for motor in MOTORS:
                    write_command(
                        port,
                        position_frame(motor, CENTER),
                    )
                    print(f"  Motor {motor}: center command sent")

                time.sleep(2.0)

            except Exception as exc:
                print(
                    f"WARNING: Could not complete center cleanup: {exc}",
                    file=sys.stderr,
                )

            port.close()

        if csv_file is not None:
            csv_file.close()

    print(f"\nCSV saved: {Path(args.csv).resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
