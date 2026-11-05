#!/usr/bin/env python3
"""Controlled H3 actuator calibration/diagnostic tool.

This tool intentionally uses the v0.3.5.1 SMC3Transport unchanged:
MotorCommand -> CommandHub -> SerialTransport -> pyserial.
It commands one motor at a time while holding the other two at center.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from smc3 import CENTER_POSITION, MAX_POSITION, MIN_POSITION, MOTORS, SMC3Transport

DEFAULT_STEP = 20
DEFAULT_START_OFFSET = -100
DEFAULT_END_OFFSET = 100
DEFAULT_SETTLE = 1.0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Controlled one-motor-at-a-time H3 SMC3 calibration diagnostic."
    )
    parser.add_argument("port", help="Serial port, e.g. /dev/ttyACM0")
    parser.add_argument("--debug", action="store_true", help="Print transmitted frames")
    parser.add_argument("--step", type=int, default=DEFAULT_STEP,
                        help=f"Sweep step in SMC3 counts (default: {DEFAULT_STEP})")
    parser.add_argument("--start", type=int, default=DEFAULT_START_OFFSET,
                        help=f"Starting offset from 512 (default: {DEFAULT_START_OFFSET})")
    parser.add_argument("--end", type=int, default=DEFAULT_END_OFFSET,
                        help=f"Ending offset from 512 (default: {DEFAULT_END_OFFSET})")
    parser.add_argument("--settle", type=float, default=DEFAULT_SETTLE,
                        help=f"Seconds to wait at each position (default: {DEFAULT_SETTLE})")
    parser.add_argument("--no-observe", action="store_true",
                        help="Run sweeps continuously without observation prompts")
    parser.add_argument("--output", type=Path, default=None,
                        help="Optional CSV file for observations")
    return parser.parse_args()


def validate_args(args: argparse.Namespace) -> None:
    if args.step <= 0:
        raise ValueError("--step must be greater than zero")
    if args.start > args.end:
        raise ValueError("--start must not be greater than --end")
    if args.settle < 0:
        raise ValueError("--settle must not be negative")

    for offset in (args.start, args.end):
        position = CENTER_POSITION + offset
        if not MIN_POSITION <= position <= MAX_POSITION:
            raise ValueError(
                f"offset {offset:+d} produces position {position}; "
                f"valid positions are {MIN_POSITION}..{MAX_POSITION}"
            )


def positions_for_sweep(start: int, end: int, step: int) -> list[int]:
    """Return inclusive offset sequence, handling a final partial step."""
    values = list(range(start, end + 1, step))
    if not values or values[-1] != end:
        values.append(end)
    return values


def set_one_motor(transport: SMC3Transport, motor: str, position: int) -> None:
    values = [CENTER_POSITION, CENTER_POSITION, CENTER_POSITION]
    values[MOTORS.index(motor)] = position
    transport.set_positions(*values)


def write_observation(writer: csv.writer | None, motor: str, position: int,
                      offset: int, observation: str) -> None:
    if writer is None:
        return
    timestamp = dt.datetime.now().astimezone().isoformat(timespec="milliseconds")
    writer.writerow([timestamp, motor, position, offset, observation])


def main() -> int:
    args = parse_args()
    try:
        validate_args(args)
    except ValueError as exc:
        print(f"Argument error: {exc}")
        return 2

    transport = SMC3Transport(args.port, debug=args.debug)
    csv_file = None
    writer = None

    if args.output is not None:
        csv_file = args.output.open("a", newline="", encoding="utf-8")
        writer = csv.writer(csv_file)
        if args.output.stat().st_size == 0:
            writer.writerow(["timestamp", "motor", "position", "offset", "observation"])

    transport.start()
    print(f"Opened {args.port}; writer thread: {transport.thread_status()}")
    print("Motors are NOT automatically enabled.")
    print("Commands: e, center, sweep a, sweep b, sweep c, status, q")
    print(f"Default sweep: offset {args.start:+d} to {args.end:+d}, step {args.step}, settle {args.settle:.2f}s")
    if args.no_observe:
        print("Observation prompts are disabled (--no-observe).")
    if args.output:
        print(f"Observations will be appended to: {args.output}")

    try:
        while True:
            for message in transport.pop_events():
                print(message)

            try:
                command = input("> ").strip().lower()
            except EOFError:
                command = "q"

            if command == "q":
                return 0
            if command == "e":
                transport.enable()
                print("sent: [ena]")
                continue
            if command == "center":
                transport.set_positions(CENTER_POSITION, CENTER_POSITION, CENTER_POSITION)
                transport.wait_for_idle(2.0)
                print("sent: A=B=C=512")
                continue
            if command == "status":
                for message in transport.pop_events():
                    print(message)
                print(transport.status())
                continue
            if command.startswith("sweep "):
                motor = command.split(maxsplit=1)[1].upper()
                if motor not in MOTORS:
                    print("Usage: sweep a | sweep b | sweep c")
                    continue
                run_sweep(transport, motor, args, writer, csv_file)
                continue

            print("Unknown command")
    except KeyboardInterrupt:
        print("\nInterrupted; returning H3 to center...")
        return 130
    finally:
        try:
            transport.set_positions(CENTER_POSITION, CENTER_POSITION, CENTER_POSITION)
            transport.wait_for_idle(2.0)
            print("H3 center command sent.")
        except Exception as exc:
            print(f"Could not send center command: {exc}")
        transport.close()
        if csv_file is not None:
            csv_file.close()


def run_sweep(transport: SMC3Transport, motor: str, args: argparse.Namespace,
              writer: csv.writer | None, csv_file) -> None:
    offsets = positions_for_sweep(args.start, args.end, args.step)
    print(f"\n--- {motor} sweep: {len(offsets)} positions ---")
    if args.no_observe:
        print("Other motors remain at 512. Observation prompts disabled; sweep runs continuously.")
    else:
        print("Other motors remain at 512. Enter an observation, or press Enter for none.")
        print("Enter q during an observation prompt to abort the sweep and return to center.")

    for offset in offsets:
        position = CENTER_POSITION + offset
        set_one_motor(transport, motor, position)
        transport.wait_for_idle(2.0)
        if args.settle:
            time.sleep(args.settle)

        print(f"{motor}={position} (offset {offset:+d})")
        if args.no_observe:
            observation = ""
        else:
            try:
                observation = input("  observation [Enter=none, q=abort]: ").strip()
            except EOFError:
                observation = ""
            if observation.lower() == "q":
                print("Sweep aborted.")
                return
        write_observation(writer, motor, position, offset, observation)
        if csv_file is not None:
            csv_file.flush()

    print(f"{motor} sweep complete.")


if __name__ == "__main__":
    raise SystemExit(main())
