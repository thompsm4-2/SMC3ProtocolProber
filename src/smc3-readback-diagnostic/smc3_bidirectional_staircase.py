
#!/usr/bin/env python3
"""
SMC3 bidirectional staircase diagnostic.

Measures feedback while approaching the same command positions
from ascending and descending directions.

Select the tested motor with --motor A, B, or C.
The other two motors remain at command 512.

The feedback x4 conversion remains a candidate interpretation.
"""

import argparse
import csv
import sys
import time
from datetime import datetime
from pathlib import Path

import serial


BAUDRATE = 500000
START_COMMAND = 537
END_COMMAND = 557
STEP = 5
TARGET_FEEDBACK = 512
MOTOR_CENTER = 512


def position_frame(motor, position):
    return bytes([
        0x5B,
        ord(motor),
        (position >> 8) & 0xFF,
        position & 0xFF,
        0x5D,
    ])


def set_position(ser, motor, position):
    frame = position_frame(motor, position)
    ser.write(frame)
    ser.flush()

    print(
        f"Command {motor} = {position} "
        f"({frame.hex(' ').upper()})"
    )


def read_feedback(ser, motor):
    ser.write(f"[rd{motor}]".encode("ascii"))
    ser.flush()

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
            f"Invalid response: {frame.hex(' ').upper()}"
        )

    return {
        "frame": frame,
        "feedback_raw": frame[2],
        "target_raw": frame[3],
        "feedback": frame[2] * 4,
        "target": frame[3] * 4,
    }


def capture_position(
    ser,
    writer,
    motor,
    command,
    direction,
    samples,
    interval,
    settle,
    sequence,
    start_time,
):
    print(
        f"\n{direction.upper()}: "
        f"command {motor} = {command}"
    )

    set_position(ser, motor, command)

    print(f"Settling for {settle:.1f} seconds...")
    time.sleep(settle)

    readings = []

    for sample_index in range(1, samples + 1):
        result = read_feedback(ser, motor)

        feedback = result["feedback"]
        error = feedback - TARGET_FEEDBACK

        writer.writerow({
            "timestamp": datetime.now().isoformat(
                timespec="milliseconds"
            ),
            "elapsed_s": round(
                time.monotonic() - start_time, 4
            ),
            "sequence": sequence,
            "direction": direction,
            "sample_index": sample_index,
            "motor": motor,
            "commanded_position": command,
            "feedback_response_hex":
                result["frame"].hex(" ").upper(),
            "feedback_raw": result["feedback_raw"],
            "feedback_x4_candidate": feedback,
            "target_raw": result["target_raw"],
            "target_x4_candidate": result["target"],
            "error_from_512": error,
        })

        readings.append(feedback)

        print(
            f"  Sample {sample_index:02d}: "
            f"feedback={feedback:3d}, "
            f"error={error:+4d}, "
            f"raw={result['feedback_raw']:3d}, "
            f"target_raw={result['target_raw']:3d}"
        )

        sequence += 1

        if sample_index < samples:
            time.sleep(interval)

    ordered = sorted(readings)
    median = ordered[len(ordered) // 2]

    print(
        f"  Summary: min={min(readings)}, "
        f"max={max(readings)}, median={median}"
    )

    return sequence, {
        "command": command,
        "direction": direction,
        "min": min(readings),
        "max": max(readings),
        "median": median,
    }


def main():
    parser = argparse.ArgumentParser(
        description="SMC3 bidirectional staircase diagnostic."
    )

    parser.add_argument(
        "--port",
        default="/dev/ttyACM0"
    )
    parser.add_argument(
        "--motor",
        type=str.upper,
        choices=["A", "B", "C"],
        default="A",
        help="Motor to test (default: A)"
    )
    parser.add_argument(
        "--start",
        type=int,
        default=START_COMMAND
    )
    parser.add_argument(
        "--end",
        type=int,
        default=END_COMMAND
    )
    parser.add_argument(
        "--step",
        type=int,
        default=STEP
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
        default=None
    )

    args = parser.parse_args()

    if not 0 <= args.start <= 1023:
        parser.error("--start must be between 0 and 1023")

    if not 0 <= args.end <= 1023:
        parser.error("--end must be between 0 and 1023")

    if args.end <= args.start:
        parser.error("--end must be greater than --start")

    if args.step <= 0:
        parser.error("--step must be positive")

    if (args.end - args.start) % args.step != 0:
        parser.error(
            "The range must be evenly divisible by --step"
        )

    if args.samples < 1:
        parser.error("--samples must be at least 1")

    if args.settle < 0 or args.interval < 0:
        parser.error("Timing values cannot be negative")

    if args.csv is None:
        csv_path = Path(
            f"smc3_motor_{args.motor}_bidirectional_staircase.csv"
        )
    else:
        csv_path = Path(args.csv)

    ascending = list(
        range(args.start, args.end + 1, args.step)
    )

    descending = list(reversed(ascending[:-1]))

    stages = [
        ("ascending", command)
        for command in ascending
    ] + [
        ("descending", command)
        for command in descending
    ]

    other_motors = [
        motor for motor in ("A", "B", "C")
        if motor != args.motor
    ]

    fieldnames = [
        "timestamp",
        "elapsed_s",
        "sequence",
        "direction",
        "sample_index",
        "motor",
        "commanded_position",
        "feedback_response_hex",
        "feedback_raw",
        "feedback_x4_candidate",
        "target_raw",
        "target_x4_candidate",
        "error_from_512",
    ]

    print(
        f"\nSMC3 MOTOR {args.motor} "
        "BIDIRECTIONAL STAIRCASE"
    )
    print("------------------------------------")
    print(f"Port:          {args.port}")
    print(f"Test motor:    {args.motor}")
    print(f"Other motors:  {other_motors} at 512")
    print(f"Ascending:     {ascending}")
    print(f"Descending:    {descending}")
    print(f"Step:          {args.step}")
    print(f"Settle:        {args.settle}s")
    print(f"Samples:       {args.samples}")
    print(f"Interval:      {args.interval}s")
    print(f"CSV:           {csv_path}")
    print()

    start_time = time.monotonic()
    sequence = 1
    summaries = []

    try:
        with serial.Serial(
            args.port,
            baudrate=BAUDRATE,
            timeout=0.5,
            write_timeout=0.5,
        ) as ser:

            with csv_path.open("w", newline="") as csv_file:
                writer = csv.DictWriter(
                    csv_file,
                    fieldnames=fieldnames
                )
                writer.writeheader()
                csv_file.flush()

                print("Waiting 2 seconds for controller startup...")
                time.sleep(2)

                ser.write(b"[ena]")
                ser.flush()
                print("Motors enabled.")

                # Initialize all motors at command 512.
                for motor in ("A", "B", "C"):
                    set_position(ser, motor, MOTOR_CENTER)

                # Move only the selected motor to its start command.
                if args.start != MOTOR_CENTER:
                    set_position(ser, args.motor, args.start)

                for direction, command in stages:
                    sequence, summary = capture_position(
                        ser=ser,
                        writer=writer,
                        motor=args.motor,
                        command=command,
                        direction=direction,
                        samples=args.samples,
                        interval=args.interval,
                        settle=args.settle,
                        sequence=sequence,
                        start_time=start_time,
                    )

                    summaries.append(summary)
                    csv_file.flush()

                print("\nRestoring final positions...")

                for motor in ("A", "B", "C"):
                    position = (
                        args.start
                        if motor == args.motor
                        else MOTOR_CENTER
                    )
                    set_position(ser, motor, position)

    except KeyboardInterrupt:
        print("\nInterrupted by user.")
        return 130

    except (
        serial.SerialException,
        TimeoutError,
        ValueError,
    ) as exc:
        print(f"\nERROR: {exc}", file=sys.stderr)
        return 1

    print("\nBIDIRECTIONAL COMPARISON")
    print("------------------------")
    print(
        f"{'Command':>8} "
        f"{'Ascending':>12} "
        f"{'Descending':>12} "
        f"{'Difference':>12}"
    )

    ascending_results = {
        item["command"]: item["median"]
        for item in summaries
        if item["direction"] == "ascending"
    }

    descending_results = {
        item["command"]: item["median"]
        for item in summaries
        if item["direction"] == "descending"
    }

    for command in sorted(descending_results):
        up = ascending_results[command]
        down = descending_results[command]

        print(
            f"{command:8d} "
            f"{up:12d} "
            f"{down:12d} "
            f"{down - up:+12d}"
        )

    print(f"\nCSV saved: {csv_path.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
