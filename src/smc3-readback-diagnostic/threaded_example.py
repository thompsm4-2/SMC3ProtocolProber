#!/usr/bin/env python3
"""SMC3 Incremental Readback Diagnostic Tool (Complete Integration)"""
import sys
import time
import csv
import argparse
import serial

# Constants & Setup
MOTORS = {"A", "B", "C"}
DELTA = 100
CENTER = 512
BAUD = 500000
FEEDBACK_COMMANDS = {m: bytes([0x5B, ord(m), 0x5D]) for m in MOTORS}

# Citation 3 & 2 CSV fields
CSV_FIELDS = [
    "timestamp", "elapsed_s", "sequence", "motor", "phase",
    "direction", "reversal", "step", "commanded_position",
    "position_command_hex", "feedback_command_hex", "feedback_response_hex",
    "framing_valid", "feedback_raw", "target_raw",
    "feedback_x4_candidate", "target_x4_candidate", "error"
]

# === CITATION 1: Low-level SMC3 Protocol Handling ===
def position_frame(motor, position):
    if motor not in MOTORS:
        raise ValueError(f"Invalid motor: {motor}")
    if not 0 <= position <= 1023:
        raise ValueError(f"Position outside SMC3 range: {position}")
    return bytes((
        0x5B, ord(motor), (position >> 8) & 0xFF, position & 0xFF, 0x5D,
    ))

def write_command(port, command):
    written = port.write(command)
    if written != len(command):
        raise IOError(f"Short serial write: {written}/{len(command)} bytes")
    port.flush()

def read_response(port, timeout):
    deadline = time.monotonic() + timeout
    response = bytearray()
    started = False

    while time.monotonic() < deadline:
        byte = port.read(1)
        if not byte: continue
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
    if len(response) != 5 or response[0] != 0x5B or response[4] != 0x5D:
        return None, None, False
    if response[1] != ord(motor):
        return None, None, False

    feedback_raw = response[2]
    target_raw = response[3]
    return feedback_raw, target_raw, True

def query_feedback(port, motor, timeout):
    """Helper to read and decode feedback (called in Citation 2)"""
    response = read_response(port, timeout)
    return FEEDBACK_COMMANDS[motor], response, decode_feedback(response, motor)

# === CITATION 2: Step-by-Step Movement & CSV Logging ===
def run_phase(port, writer, motor, phase_name, start_pos, end_pos, direction, reversal, sequence, start_time):
    position = start_pos
    step_count = abs(end_pos - start_pos)

    print(f"\n{motor}: {phase_name} {start_pos} -> {end_pos}")
    for step in range(1, step_count + 1):
        position += direction
        pos_cmd = position_frame(motor, position)
        error = ""

        try:
            write_command(port, pos_cmd)
            fb_cmd, resp, feedback, target, valid = query_feedback(port, motor, timeout=0.25)

            if not valid:
                error = "INVALID_OR_MISSING_FEEDBACK"

        except Exception as exc:
            fb_cmd = FEEDBACK_COMMANDS[motor]
            resp = b""
            feedback, target = None, None
            valid = False
            error = str(exc)

        sequence += 1
        elapsed = time.monotonic() - start_time
        is_first_reversal = int(reversal and step == 1)

        writer.writerow({
            "timestamp": datetime.datetime.now().isoformat(),
            "elapsed_s": f"{elapsed:.6f}",
            "sequence": sequence,
            "motor": motor,
            "phase": phase_name,
            "direction": direction,
            "reversal": is_first_reversal,
            "step": step,
            "commanded_position": position,
            "position_command_hex": pos_cmd.hex(" ").upper(),
            "feedback_command_hex": fb_cmd.hex(" ").upper(),
            "feedback_response_hex": resp.hex(" ").upper(),
            "framing_valid": valid,
            "feedback_raw": feedback if feedback is not None else "",
            "target_raw": target if target is not None else "",
            "feedback_x4_candidate": feedback * 4 if feedback is not None else "",
            "target_x4_candidate": target * 4 if target is not None else "",
            "error": error,
        })

# === CITATION 3: Argument Parsing & Main Execution ===
def parse_args():
    parser = argparse.ArgumentParser(description="Incremental SMC3 feedback/readback diagnostic")
    parser.add_argument("--port", required=True, help="SMC3 serial port (e.g., /dev/ttyACM0)")
    parser.add_argument("--motor", required=True, choices=["A", "B", "C", "ALL"], help="Motor to test")
    parser.add_argument("--active", action="store_true", help="Required confirmation before sending motor commands")
    parser.add_argument("--delta", type=int, default=DELTA, help="Excursion from center (min 100)")
    parser.add_argument("--interval", type=float, default=0.05, help="Delay between command/readback cycles")
    parser.add_argument("--read-timeout", type=float, default=0.25, help="Feedback response timeout (s)")
    parser.add_argument("--csv", default="smc3_incremental_readback.csv", help="Output CSV path")

    args = parser.parse_args()
    if not args.active:
        parser.error("--active is required for motor movement")
    if args.delta < 100:
        parser.error("--delta must be at least 100")
    return args

if __name__ == "__main__":
    import datetime

    args = parse_args()

    # CSV Creation (Citation 3 & 2)
    csv_file = open(args.csv, "w", newline="", encoding="utf-8")
    writer = csv.DictWriter(csv_file, fieldnames=CSV_FIELDS)
    writer.writeheader()

    try:
        with serial.Serial(port=args.port, baudrate=BAUD, timeout=0.1) as port:
            print(f"Connected to {args.port} @ {BAUD} baud")

            # Center motors first
            for m in ("A", "B", "C"):
                if m == args.motor or args.motor == "ALL":
                    write_command(port, position_frame(m, CENTER))
                time.sleep(args.interval)

            # Run diagnostic phases (simplified from citation 3 structure)
            sequence = 0
            start_time = time.monotonic()

            for motor in ("A", "B", "C") if args.motor == "ALL" else [args.motor]:
                run_phase(port, writer, motor, "center_to_delta", CENTER, CENTER + DELTA, 1, False, sequence, start_time)
                run_phase(port, writer, motor, "delta_return", CENTER + DELTA, CENTER - DELTA, -1, True, sequence, start_time)

    finally:
        csv_file.close()
        print(f"\nDone. Results saved to {args.csv}")
