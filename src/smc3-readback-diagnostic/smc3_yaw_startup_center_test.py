
#!/usr/bin/env python3
"""
SMC3 yaw startup / center-command diagnostic.

This test intentionally sends NO position commands to motors A or B.

Sequence:
  1. Open serial port and allow the controller to restart.
  2. Read feedback for A, B, and C before enabling motors.
  3. Send [ena], wait, and read feedback again.
  4. Send ONLY the C=512 position command, wait, and read feedback.
  5. Exit without sending any restore or additional position commands.

The feedback x4 conversion is recorded as a candidate interpretation only.
"""

import argparse
import csv
import sys
import time
from datetime import datetime

import serial


BAUD_RATE = 500000
MOTORS = ("A", "B", "C")


def smc3_command(command):
    return b"[" + command.encode("ascii") + b"]"


def position_frame(motor, position):
    if motor not in MOTORS:
        raise ValueError(f"Invalid motor: {motor}")
    if not 0 <= position <= 1023:
        raise ValueError(f"Position out of range: {position}")

    return bytes((
        0x5B,
        ord(motor),
        (position >> 8) & 0x03,
        position & 0xFF,
        0x5D,
    ))


def read_feedback(ser, motor):
    """Read one five-byte [rdX] response."""
    ser.reset_input_buffer()
    ser.write(smc3_command(f"rd{motor}"))
    ser.flush()

    response = ser.read(5)

    if len(response) != 5:
        raise RuntimeError(
            f"Motor {motor}: expected 5 response bytes, got "
            f"{len(response)}: {response.hex(' ').upper()}"
        )

    if (
        response[0] != 0x5B
        or response[1] != ord(motor)
        or response[4] != 0x5D
    ):
        raise RuntimeError(
            f"Motor {motor}: invalid response framing: "
            f"{response.hex(' ').upper()}"
        )

    feedback_raw = response[2]
    target_raw = response[3]

    return {
        "motor": motor,
        "response_hex": response.hex(" ").upper(),
        "feedback_raw": feedback_raw,
        "feedback_x4_candidate": feedback_raw * 4,
        "target_raw": target_raw,
        "target_x4_candidate": target_raw * 4,
    }


def read_all_feedback(
    ser, writer, csv_file, phase, start_time, samples, interval
):
    print(f"\n{phase}")
    print("-" * len(phase))

    for sample_index in range(1, samples + 1):
        timestamp = datetime.now().isoformat(timespec="milliseconds")
        elapsed = time.monotonic() - start_time

        readings = []

        for motor in MOTORS:
            result = read_feedback(ser, motor)
            readings.append(result)

            writer.writerow({
                "timestamp": timestamp,
                "elapsed_s": f"{elapsed:.3f}",
                "phase": phase,
                "sample": sample_index,
                "motor": motor,
                "response_hex": result["response_hex"],
                "feedback_raw": result["feedback_raw"],
                "feedback_x4_candidate":
                    result["feedback_x4_candidate"],
                "target_raw": result["target_raw"],
                "target_x4_candidate":
                    result["target_x4_candidate"],
            })

        csv_file.flush()

        summary = " | ".join(
            f"{r['motor']}: feedback={r['feedback_x4_candidate']} "
            f"(raw={r['feedback_raw']}), "
            f"target={r['target_x4_candidate']} "
            f"(raw={r['target_raw']})"
            for r in readings
        )
        print(f"  Sample {sample_index:02d}: {summary}")

        if sample_index < samples and interval > 0:
            time.sleep(interval)


def main():
    parser = argparse.ArgumentParser(
        description="Isolate SMC3 yaw startup and C=512 centering behavior."
    )
    parser.add_argument(
        "--port", required=True,
        help="Serial port, e.g. /dev/ttyACM0"
    )
    parser.add_argument(
        "--startup-delay", type=float, default=2.0,
        help="Delay after opening serial port (default: 2s)"
    )
    parser.add_argument(
        "--settle", type=float, default=5.0,
        help="Settle time after enable and C=512 (default: 5s)"
    )
    parser.add_argument(
        "--samples", type=int, default=10,
        help="Feedback samples per phase (default: 10)"
    )
    parser.add_argument(
        "--interval", type=float, default=0.25,
        help="Delay between samples (default: 0.25s)"
    )
    parser.add_argument(
        "--csv", default="smc3_yaw_startup_center_test.csv",
        help="Output CSV path"
    )

    args = parser.parse_args()

    if args.startup_delay < 0 or args.settle < 0 or args.interval < 0:
        parser.error("timings must be non-negative")
    if args.samples < 1:
        parser.error("--samples must be at least 1")

    fieldnames = [
        "timestamp",
        "elapsed_s",
        "phase",
        "sample",
        "motor",
        "response_hex",
        "feedback_raw",
        "feedback_x4_candidate",
        "target_raw",
        "target_x4_candidate",
    ]

    start_time = time.monotonic()

    print("SMC3 YAW STARTUP / CENTER-COMMAND DIAGNOSTIC")
    print("--------------------------------------------")
    print(f"Port:          {args.port}")
    print(f"Baud:          {BAUD_RATE}")
    print(f"Startup delay: {args.startup_delay:.1f}s")
    print(f"Settle:        {args.settle:.1f}s")
    print(f"Samples:       {args.samples}")
    print(f"Interval:      {args.interval:.2f}s")
    print(f"CSV:           {args.csv}")
    print()
    print("Position commands sent by this test:")
    print("  A: none")
    print("  B: none")
    print("  C: 512 only")
    print("No final restore command will be sent.")

    try:
        with serial.Serial(
            args.port,
            BAUD_RATE,
            timeout=0.5,
            write_timeout=0.5,
        ) as ser, open(
            args.csv, "w", newline="", encoding="utf-8"
        ) as csv_file:

            writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
            writer.writeheader()
            csv_file.flush()

            print(
                f"\nWaiting {args.startup_delay:.1f}s "
                "for controller startup..."
            )
            time.sleep(args.startup_delay)

            read_all_feedback(
                ser, writer, csv_file,
                "BEFORE MOTOR ENABLE",
                start_time, args.samples, args.interval
            )

            print("\nSending motor enable command [ena]...")
            ser.write(smc3_command("ena"))
            ser.flush()

            print(f"Waiting {args.settle:.1f}s after motor enable.")
            time.sleep(args.settle)

            read_all_feedback(
                ser, writer, csv_file,
                "AFTER ENABLE - BEFORE POSITION COMMAND",
                start_time, args.samples, args.interval
            )

            print("\nSending the ONLY position command: C = 512")
            frame = position_frame("C", 512)
            print(f"Command C = 512 ({frame.hex(' ').upper()})")
            ser.write(frame)
            ser.flush()

            print(f"Waiting {args.settle:.1f}s after C=512.")
            time.sleep(args.settle)

            read_all_feedback(
                ser, writer, csv_file,
                "AFTER C=512",
                start_time, args.samples, args.interval
            )

            print("\nTest complete. No further position commands sent.")
            print(f"CSV saved: {args.csv}")

    except (serial.SerialException, OSError, RuntimeError) as exc:
        print(f"\nERROR: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
