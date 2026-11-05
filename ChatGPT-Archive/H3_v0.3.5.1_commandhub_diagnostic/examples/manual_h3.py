#!/usr/bin/env python3
"""Manual diagnostic control for an H3 SMC3 transport."""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from smc3 import CENTER_POSITION, SMC3Transport


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("port")
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()

    transport = SMC3Transport(args.port, debug=args.debug)
    transport.start()
    print(f"Opened {args.port}; writer thread: {transport.thread_status()}")
    print("Motors are NOT automatically enabled.")
    print("Commands: a+/a-, b+/b-, c+/c-, center, e, s, status, ver, q")
    print("This diagnostic version uses a CommandHub worker thread and per-motor latest-value-wins queue.")
    print("Debug TX messages are collected by the main thread so they do not")
    print("overwrite the input prompt.")

    values = [CENTER_POSITION] * 3
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
            if command == "s":
                transport.stop()
                print("sent: []")
                continue
            if command == "ver":
                transport.version()
                print("sent: [ver]")
                continue
            if command == "status":
                for message in transport.pop_events():
                    print(message)
                print(transport.status())
                continue
            if command == "center":
                values[:] = [CENTER_POSITION] * 3
                transport.set_positions(*values)
                print("sent: A=B=C=512")
                continue
            if len(command) == 2 and command[0] in "abc" and command[1] in "+-":
                index = "abc".index(command[0])
                values[index] = max(0, min(1023, values[index] + (10 if command[1] == "+" else -10)))
                transport.set_positions(*values)
                print(f"sent: A={values[0]} B={values[1]} C={values[2]}")
                continue
            print("Unknown command")
    finally:
        transport.close()


if __name__ == "__main__":
    raise SystemExit(main())
