
#!/usr/bin/env python3
"""
SMC3 Motor A feedback-centering diagnostic.

Find the motor A command position that produces feedback 512.

Known observed direction:
    Increasing A command -> decreasing A feedback.

The script:
    1. Opens the SMC3 serial connection.
    2. Enables the motors.
    3. Commands A, B and C to 512.
    4. Waits for the platform to settle.
    5. Measures the initial feedback.
    6. Adjusts A in 5-count increments.
    7. Records every feedback response in CSV.
    8. Stops at feedback 512, an overshoot, unexpected
       feedback direction, or a command safety limit.

Feedback multiplied by four is recorded as a candidate
decoding, not an independently verified firmware rule.
"""

import argparse
import csv
import sys
import time
from datetime import datetime
from pathlib import Path

import serial


TARGET_FEEDBACK = 512
DEFAULT_STEP = 5
DEFAULT_MIN_COMMAND = 412
DEFAULT_MAX_COMMAND = 612

BAUDRATE = 500000
SERIAL_TIMEOUT = 0.5


def position_command(motor, position):
    """Build an SMC3 position command."""
    return bytes([
        0x5B,
        ord(motor),
        (position >> 8) & 0xFF,
        position & 0xFF,
        0x5D,
    ])


def read_command(motor):
    """Build an SMC3 feedback-read command."""
    return f"[rd{motor}]".encode("ascii")


def enable_motors(ser):
    ser.write(b"[ena]")
    ser.flush()
    print("Motors enabled.")


def set_position(ser, motor, position):
    if not 0 <= position <= 1023:
        raise ValueError(f"Invalid position: {position}")

    command = position_command(motor, position)
    ser.write(command)
    ser.flush()

    print(
        f"Command {motor} = {position:4d} "
        f"({command.hex(' ').upper()})"
    )


def read_feedback(ser, motor):
    """Read and validate one five-byte SMC3 feedback response."""

    ser.write(read_command(motor))
    ser.flush()

    # Find the response start marker.
    while True:
        first = ser.read(1)

        if not first:
            raise TimeoutError(
                f"Timeout waiting for motor {motor} response"
            )

        if first == b"[":
            break

    remainder = ser.read(4)

    if len(remainder) != 4:
        raise TimeoutError(
            f"Incomplete response from motor {motor}"
        )

    frame = first + remainder

    if frame[1] != ord(motor) or frame[4] != ord("]"):
        raise ValueError(
            f"Invalid response for motor {motor}: "
            f"{frame.hex(' ').upper()}"
        )

    feedback_raw = frame[2]
    target_raw = frame[3]

    return {
        "frame": frame,
        "feedback_raw": feedback_raw,
        "target_raw": target_raw,
        "feedback_candidate": feedback_raw * 4,
        "target_candidate": target_raw * 4,
    }


def capture_feedback(ser, motor, command, writer, sequence,
                     start_time, samples=5, interval=0.25):

    readings = []

    for _ in range(samples):
        result = read_feedback(ser, motor)
        timestamp = datetime.now().isoformat(timespec="milliseconds")
        elapsed = time.monotonic() - start_time

        feedback = result["feedback_candidate"]
        error = feedback - TARGET_FEEDBACK

        writer.writerow({
            "timestamp": timestamp,
            "elapsed_s": round(elapsed, 4),
            "sequence": sequence,
            "motor": motor,
            "commanded_position": command,
            "feedback_response_hex":
                result["frame"].hex(" ").upper(),
            "feedback_raw": result["feedback_raw"],
            "feedback_x4_candidate": feedback,
            "target_raw": result["target_raw"],
            "target_x4_candidate": result["target_candidate"],
            "error_from_512": error,
        })

        readings.append(feedback)
        sequence += 1

        time.sleep(interval)

    return readings, sequence


def main():
    parser = argparse.ArgumentParser(
        description="Find the command that produces A feedback 512."
    )

    parser.add_argument("--port", default="/dev/ttyACM0")
    parser.add_argument("--step", type=int, default=DEFAULT_STEP)
    parser.add_argument("--min-command", type=int,
                        default=DEFAULT_MIN_COMMAND)
    parser.add_argument("--max-command", type=int,
                        default=DEFAULT_MAX_COMMAND)
    parser.add_argument("--settle", type=float, default=2.5)
    parser.add_argument("--samples", type=int, default=5)
    parser.add_argument("--sample-interval", type=float, default=0.25)
    parser.add_argument(
        "--csv",
        default="smc3_motor_A_feedback_center_search.csv"
    )

    args = parser.parse_args()

    if args.step <= 0:
        parser.error("--step must be positive")

    if not args.min_command < 512 < args.max_command:
        parser.error("Command limits must surround 512")

    if args.samples < 1:
        parser.error("--samples must be at least 1")

    csv_path = Path(args.csv)
    start_time = time.monotonic()
    sequence = 0

    print("\nSMC3 MOTOR A FEEDBACK CENTER SEARCH")
    print("----------------------------------")
    print(f"Port:          {args.port}")
    print(f"Target feedback: {TARGET_FEEDBACK}")
    print(f"Step size:     {args.step}")
    print(f"Command limits: {args.min_command} to {args.max_command}")
    print(f"Settle time:   {args.settle} seconds")
    print(f"CSV:           {csv_path}")
    print()

    fieldnames = [
        "timestamp",
        "elapsed_s",
        "sequence",
        "motor",
        "commanded_position",
        "feedback_response_hex",
        "feedback_raw",
        "feedback_x4_candidate",
        "target_raw",
        "target_x4_candidate",
        "error_from_512",
    ]

    try:
        with serial.Serial(
            args.port,
            baudrate=BAUDRATE,
            timeout=SERIAL_TIMEOUT,
            write_timeout=SERIAL_TIMEOUT,
        ) as ser, csv_path.open("w", newline="") as csv_file:

            writer = csv.DictWriter(
                csv_file,
                fieldnames=fieldnames
            )
            writer.writeheader()

            print("Waiting 2 seconds for controller startup...")
            time.sleep(2)

            enable_motors(ser)

            # Establish the nominal center for all motors.
            for motor in ("A", "B", "C"):
                set_position(ser, motor, 512)

            print("\nWaiting for initial settling...")
            time.sleep(5)

            command = 512

            readings, sequence = capture_feedback(
                ser, "A", command, writer, sequence,
                start_time, args.samples, args.sample_interval
            )

            feedback = sorted(readings)[len(readings) // 2]
            error = feedback - TARGET_FEEDBACK

            print("\nInitial measurement")
            print(f"Command A:  {command}")
            print(f"Feedback A: {feedback}")
            print(f"Error:      {error:+d}")

            if error == 0:
                print("\nSUCCESS: Command 512 produces feedback 512.")

            else:
                previous_error = error
                previous_feedback = feedback
                iteration = 0

                while True:
                    # A+ decreases feedback; A- increases feedback.
                    direction = 1 if error > 0 else -1
                    next_command = command + direction * args.step

                    if not args.min_command <= next_command <= args.max_command:
                        print("\nSTOP: Command safety limit reached.")
                        break

                    iteration += 1
                    print(
                        f"\nAdjustment {iteration}: "
                        f"A {command} -> {next_command}"
                    )

                    set_position(ser, "A", next_command)
                    command = next_command

                    print(f"Waiting {args.settle} seconds...")
                    time.sleep(args.settle)

                    readings, sequence = capture_feedback(
                        ser, "A", command, writer, sequence,
                        start_time, args.samples,
                        args.sample_interval
                    )

                    feedback = sorted(readings)[len(readings) // 2]
                    error = feedback - TARGET_FEEDBACK

                    print(f"Command A:  {command}")
                    print(f"Feedback A: {feedback}")
                    print(f"Error:      {error:+d}")

                    if error == 0:
                        print(
                            "\nSUCCESS: Found command producing "
                            "feedback 512."
                        )
                        break

                    # Stop if feedback crossed the target.
                    if (previous_error > 0 and error < 0) or (
                        previous_error < 0 and error > 0
                    ):
                        print(
                            "\nSTOP: Feedback crossed 512. "
                            "Nearest tested values recorded."
                        )
                        break

                    # Stop if feedback moved in the wrong direction.
                    if abs(error) > abs(previous_error):
                        print(
                            "\nSTOP: Feedback moved farther from "
                            "the target. Check direction or settling."
                        )
                        break

                    if feedback == previous_feedback:
                        print(
                            "\nWARNING: Feedback did not change "
                            "at this command."
                        )

                    previous_error = error
                    previous_feedback = feedback

            csv_file.flush()

            print("\nSearch finished.")
            print(f"Last command:  {command}")
            print(f"Last feedback: {feedback}")
            print(f"CSV saved:     {csv_path.resolve()}")

    except (serial.SerialException, TimeoutError, ValueError) as exc:
        print(f"\nERROR: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
