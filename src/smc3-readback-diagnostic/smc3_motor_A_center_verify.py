
#!/usr/bin/env python3
"""
SMC3 Motor A calibrated-center verification.

Tests whether command A=537 consistently produces
feedback A=512, including returns from both directions.

Sequence:
    A=537  Initial baseline
    A=612  Positive excursion
    A=537  Return from positive
    A=412  Negative excursion
    A=537  Return from negative

B and C remain commanded to 512.

Raw feedback bytes are preserved. Feedback x4 is a
candidate decoding, not a verified firmware rule.
"""

import argparse
import csv
import sys
import time
from datetime import datetime
from pathlib import Path

import serial


BAUDRATE = 500000
TARGET_FEEDBACK = 512

CENTER_COMMAND = 537
POSITIVE_COMMAND = 612
NEGATIVE_COMMAND = 412

SEQUENCE = [
    ("initial_center", CENTER_COMMAND),
    ("positive_excursion", POSITIVE_COMMAND),
    ("return_from_positive", CENTER_COMMAND),
    ("negative_excursion", NEGATIVE_COMMAND),
    ("return_from_negative", CENTER_COMMAND),
]


def position_command(motor, position):
    return bytes([
        0x5B,
        ord(motor),
        (position >> 8) & 0xFF,
        position & 0xFF,
        0x5D,
    ])


def set_position(ser, motor, position):
    frame = position_command(motor, position)
    ser.write(frame)
    ser.flush()

    print(
        f"Command {motor} = {position} "
        f"({frame.hex(' ').upper()})"
    )


def read_feedback(ser, motor):
    ser.write(f"[rd{motor}]".encode("ascii"))
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
            f"Invalid response for {motor}: "
            f"{frame.hex(' ').upper()}"
        )

    return {
        "frame": frame,
        "feedback_raw": frame[2],
        "target_raw": frame[3],
        "feedback_candidate": frame[2] * 4,
        "target_candidate": frame[3] * 4,
    }


def capture_stage(
    ser,
    writer,
    motor,
    stage,
    command,
    samples,
    interval,
    sequence_number,
    start_time,
):
    readings = []

    print(f"\nCapturing {samples} samples: {stage}")

    for _ in range(samples):
        result = read_feedback(ser, motor)

        feedback = result["feedback_candidate"]
        error = feedback - TARGET_FEEDBACK

        writer.writerow({
            "timestamp": datetime.now().isoformat(
                timespec="milliseconds"
            ),
            "elapsed_s": round(
                time.monotonic() - start_time, 4
            ),
            "sequence": sequence_number,
            "stage": stage,
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

        print(
            f"  Feedback={feedback:3d} "
            f"Error={error:+4d} "
            f"Raw={result['feedback_raw']:3d} "
            f"Frame={result['frame'].hex(' ').upper()}"
        )

        sequence_number += 1
        time.sleep(interval)

    ordered = sorted(readings)
    median = ordered[len(ordered) // 2]

    print(
        f"  Summary: min={min(readings)}, "
        f"max={max(readings)}, "
        f"median={median}, "
        f"target={TARGET_FEEDBACK}"
    )

    return sequence_number, readings


def main():
    parser = argparse.ArgumentParser(
        description="Verify motor A command 537 center."
    )

    parser.add_argument(
        "--port",
        default="/dev/ttyACM0"
    )
    parser.add_argument(
        "--center",
        type=int,
        default=CENTER_COMMAND
    )
    parser.add_argument(
        "--positive",
        type=int,
        default=POSITIVE_COMMAND
    )
    parser.add_argument(
        "--negative",
        type=int,
        default=NEGATIVE_COMMAND
    )
    parser.add_argument(
        "--settle",
        type=float,
        default=5.0
    )
    parser.add_argument(
        "--samples",
        type=int,
        default=10
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=0.25
    )
    parser.add_argument(
        "--csv",
        default="smc3_motor_A_center_537_verification.csv"
    )

    args = parser.parse_args()

    for value in (args.center, args.positive, args.negative):
        if not 0 <= value <= 1023:
            parser.error("Command positions must be 0–1023")

    if args.samples < 1:
        parser.error("--samples must be at least 1")

    if args.settle < 0 or args.interval < 0:
        parser.error("Timing values cannot be negative")

    csv_path = Path(args.csv)

    fieldnames = [
        "timestamp",
        "elapsed_s",
        "sequence",
        "stage",
        "motor",
        "commanded_position",
        "feedback_response_hex",
        "feedback_raw",
        "feedback_x4_candidate",
        "target_raw",
        "target_x4_candidate",
        "error_from_512",
    ]

    start_time = time.monotonic()
    sequence_number = 1

    # Build the test sequence from the supplied arguments.
    stages = [
        ("initial_center", args.center),
        ("positive_excursion", args.positive),
        ("return_from_positive", args.center),
        ("negative_excursion", args.negative),
        ("return_from_negative", args.center),
    ]

    print("\nSMC3 MOTOR A CENTER VERIFICATION")
    print("--------------------------------")
    print(f"Port:          {args.port}")
    print(f"Center command: {args.center}")
    print(f"Positive:       {args.positive}")
    print(f"Negative:       {args.negative}")
    print(f"Settle time:    {args.settle}s")
    print(f"Samples/stage:  {args.samples}")
    print(f"CSV:            {csv_path}")
    print()

    summaries = []

    try:
        with serial.Serial(
            args.port,
            baudrate=BAUDRATE,
            timeout=0.5,
            write_timeout=0.5,
        ) as ser, csv_path.open("w", newline="") as csv_file:

            writer = csv.DictWriter(
                csv_file,
                fieldnames=fieldnames
            )
            writer.writeheader()

            print("Waiting 2 seconds for controller startup...")
            time.sleep(2)

            ser.write(b"[ena]")
            ser.flush()
            print("Motors enabled.")

            # Establish the initial commanded positions.
            set_position(ser, "A", args.center)
            set_position(ser, "B", 512)
            set_position(ser, "C", 512)

            for stage, command in stages:
                print(f"\n--- {stage} ---")

                set_position(ser, "A", command)

                print(f"Settling for {args.settle} seconds...")
                time.sleep(args.settle)

                sequence_number, readings = capture_stage(
                    ser=ser,
                    writer=writer,
                    motor="A",
                    stage=stage,
                    command=command,
                    samples=args.samples,
                    interval=args.interval,
                    sequence_number=sequence_number,
                    start_time=start_time,
                )

                csv_file.flush()

                summaries.append({
                    "stage": stage,
                    "command": command,
                    "min": min(readings),
                    "max": max(readings),
                    "median": sorted(readings)[
                        len(readings) // 2
                    ],
                })

            # Leave the platform at the calibrated center command.
            print("\nRestoring final center command...")
            set_position(ser, "A", args.center)
            set_position(ser, "B", 512)
            set_position(ser, "C", 512)

            csv_file.flush()

    except KeyboardInterrupt:
        print("\nInterrupted by user.")
        return 130

    except (serial.SerialException, TimeoutError, ValueError) as exc:
        print(f"\nERROR: {exc}", file=sys.stderr)
        return 1

    print("\nVERIFICATION SUMMARY")
    print("--------------------")

    for result in summaries:
        print(
            f"{result['stage']:24s} "
            f"Command={result['command']:3d} "
            f"Feedback median={result['median']:3d} "
            f"Range={result['min']}–{result['max']}"
        )

    print(f"\nCSV saved: {csv_path.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
