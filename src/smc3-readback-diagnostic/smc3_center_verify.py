
#!/usr/bin/env python3
"""
DOF Reality H3 — SMC3 center-only verification

Commands all motors to 512, allows a 5-second settling period,
then records feedback and target readbacks for 15 seconds.

No movement sweeps or excursion commands are issued.
"""

import argparse
import csv
import time
from datetime import datetime
from pathlib import Path

import serial


MOTORS = ("A", "B", "C")
CENTER = 512
BAUD_RATE = 500000

SETTLE_SECONDS = 5.0
CAPTURE_SECONDS = 15.0
SAMPLE_INTERVAL = 0.25


def position_command(motor: str, position: int) -> bytes:
    """Build an SMC3 position command."""
    if motor not in MOTORS:
        raise ValueError(f"Invalid motor: {motor}")

    if not 0 <= position <= 1023:
        raise ValueError("Position must be between 0 and 1023")

    high = (position >> 8) & 0x03
    low = position & 0xFF

    return bytes((ord("["), ord(motor), high, low, ord("]")))


def feedback_command(motor: str) -> bytes:
    """Build an SMC3 feedback read command."""
    if motor not in MOTORS:
        raise ValueError(f"Invalid motor: {motor}")

    return f"[rd{motor}]".encode("ascii")


def parse_feedback(response: bytes, expected_motor: str):
    """
    Parse a five-byte SMC3 response:
        [ motor feedback target ]

    Returns raw feedback and target bytes, or None values
    when framing or motor identification is invalid.
    """
    valid = (
        len(response) == 5
        and response[0] == ord("[")
        and response[1] == ord(expected_motor)
        and response[4] == ord("]")
    )

    if not valid:
        return False, None, None

    feedback_raw = response[2]
    target_raw = response[3]

    return True, feedback_raw, target_raw


def send_position(ser, motor: str, position: int):
    command = position_command(motor, position)
    ser.write(command)
    ser.flush()
    print(f"TX {motor} center: {command.hex(' ').upper()}")


def read_motor(ser, motor: str):
    """Request and parse one motor's feedback."""
    command = feedback_command(motor)

    ser.reset_input_buffer()
    ser.write(command)
    ser.flush()

    response = ser.read_until(b"]", size=5)

    valid, feedback_raw, target_raw = parse_feedback(
        response, motor
    )

    if valid:
        feedback_candidate = feedback_raw * 4
        target_candidate = target_raw * 4
    else:
        feedback_candidate = None
        target_candidate = None

    return {
        "feedback_command_hex": command.hex(" ").upper(),
        "response_hex": response.hex(" ").upper(),
        "response_length": len(response),
        "framing_valid": valid,
        "feedback_raw": feedback_raw,
        "target_raw": target_raw,
        "feedback_x4_candidate": feedback_candidate,
        "target_x4_candidate": target_candidate,
    }


def main():
    parser = argparse.ArgumentParser(
        description="H3 SMC3 center-only verification"
    )

    parser.add_argument(
        "--port",
        default="/dev/ttyACM0",
        help="Serial port (default: /dev/ttyACM0)",
    )

    parser.add_argument(
        "--csv",
        default="smc3_center_verification.csv",
        help="Output CSV filename",
    )

    args = parser.parse_args()

    output_path = Path(args.csv)

    rows = []

    print(f"Opening {args.port} at {BAUD_RATE} baud")

    with serial.Serial(
        port=args.port,
        baudrate=BAUD_RATE,
        timeout=0.5,
        write_timeout=0.5,
    ) as ser:

        # Allow the Arduino serial connection to initialize.
        time.sleep(2.0)

        # Enable the SMC3 controller.
        ser.write(b"[ena]")
        ser.flush()
        print("TX: [ena]")

        time.sleep(0.2)

        # Command all motors to center.
        for motor in MOTORS:
            send_position(ser, motor, CENTER)

        print(
            f"\nWaiting {SETTLE_SECONDS:.1f} seconds "
            "for the platform to settle..."
        )
        time.sleep(SETTLE_SECONDS)

        print(
            f"\nStarting {CAPTURE_SECONDS:.1f}-second "
            "center-only capture..."
        )

        capture_start = time.monotonic()
        sequence = 0

        while time.monotonic() - capture_start < CAPTURE_SECONDS:
            cycle_start = time.monotonic()
            sequence += 1

            for motor in MOTORS:
                result = read_motor(ser, motor)

                elapsed = time.monotonic() - capture_start
                timestamp = datetime.now().isoformat()

                row = {
                    "timestamp": timestamp,
                    "elapsed_s": round(elapsed, 4),
                    "sequence": sequence,
                    "motor": motor,
                    "commanded_position": CENTER,
                    **result,
                }

                rows.append(row)

                if result["framing_valid"]:
                    print(
                        f"{elapsed:7.3f}s  {motor} "
                        f"feedback={result['feedback_raw']:3d} "
                        f"target={result['target_raw']:3d} "
                        f"candidate="
                        f"{result['feedback_x4_candidate']:4d}"
                    )
                else:
                    print(
                        f"{elapsed:7.3f}s  {motor} "
                        f"INVALID RESPONSE: "
                        f"{result['response_hex']}"
                    )

            remaining = SAMPLE_INTERVAL - (
                time.monotonic() - cycle_start
            )

            if remaining > 0:
                time.sleep(remaining)

    # Write all captured rows to CSV.
    fieldnames = [
        "timestamp",
        "elapsed_s",
        "sequence",
        "motor",
        "commanded_position",
        "feedback_command_hex",
        "response_hex",
        "response_length",
        "framing_valid",
        "feedback_raw",
        "target_raw",
        "feedback_x4_candidate",
        "target_x4_candidate",
    ]

    with output_path.open("w", newline="") as csv_file:
        writer = csv.DictWriter(
            csv_file,
            fieldnames=fieldnames,
        )
        writer.writeheader()
        writer.writerows(rows)

    print(f"\nCSV saved: {output_path.resolve()}")

    # Summarize valid feedback samples.
    print("\nCENTER VERIFICATION SUMMARY")
    print("-" * 65)

    for motor in MOTORS:
        values = [
            row["feedback_x4_candidate"]
            for row in rows
            if row["motor"] == motor
            and row["framing_valid"]
        ]

        if not values:
            print(f"{motor}: No valid feedback samples")
            continue

        print(
            f"{motor}: "
            f"samples={len(values)}, "
            f"first={values[0]}, "
            f"last={values[-1]}, "
            f"min={min(values)}, "
            f"max={max(values)}, "
            f"mean={sum(values) / len(values):.2f}, "
            f"final_error={values[-1] - CENTER:+d}"
        )


if __name__ == "__main__":
    main()
