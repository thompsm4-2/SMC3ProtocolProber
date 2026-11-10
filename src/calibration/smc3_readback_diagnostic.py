#!/usr/bin/env python3
"""SMC3 Readback Diagnostic Utility for DOF Reality H3.

This utility investigates the actual SMC3 readback data stream produced by
the DOF Reality H3 controller. It captures raw serial data to establish:

1. The exact response format for uppercase readback requests [rdA], [rdB], [rdC].
2. Whether responses contain motor feedback position and target position.
3. How those values are encoded and scaled.
4. The effective resolution of the feedback position.
5. Whether the feedback can distinguish individual position units or is quantized.
6. Whether readback responses are reliable and consistently associated with requests.
7. Whether readback polling can coexist with normal motor commands.

Usage:
    Passive test of motor A:
        python smc3_readback_diagnostic.py --port /dev/ttyUSB0 --motor A --duration 30

    Passive test of all motors:
        python smc3_readback_diagnostic.py --port /dev/ttyUSB0 --motor ALL --duration 60

    Active target-resolution test:
        python smc3_readback_diagnostic.py --port /dev/ttyUSB0 --active-target-test --motor A

    Help:
        python smc3_readback_diagnostic.py --help
"""

import argparse
import csv
import datetime as dt
import io
import os
import signal
import serial
import sys
import tempfile
import time
from collections import deque
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any


# SMC3 read command bytes - uppercase as specified
READ_COMMANDS: Dict[str, bytes] = {
    "A": bytes([91, 114, 100, 65, 93]),  # [rdA]
    "B": bytes([91, 114, 100, 66, 93]),  # [rdB]
    "C": bytes([91, 114, 100, 67, 93]),  # [rdC]
}

SMC3_BAUD = 500000
CENTER = 512
MIN_POS = 0
MAX_POS = 1023

# Default polling rate: 4 requests per second per motor (0.25s interval)
DEFAULT_POLL_INTERVAL = 0.25
DEFAULT_TIMEOUT = 0.10

# Active test sequence around center
ACTIVE_TEST_SEQUENCE = [512, 513, 514, 515, 516, 520, 524]


class FakeSerial:
    """Fake serial port for testing without hardware."""

    def __init__(
        self,
        port: str = "/dev/ttyACM0",
        baudrate: int = 9600,
        timeout: float = 1.0,
        responses: Optional[List[bytes]] = None,
        write_error: bool = False,
        raise_timeout: bool = False,
    ):
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.responses = responses or []
        self.write_error = write_error
        self.raise_timeout = raise_timeout
        self._input_buffer = io.BytesIO()
        self._output_buffer = io.BytesIO()
        self._write_count = 0
        self._response_index = 0
        self._response_offset = 0  # Track offset within current response
        self._closed = False
        self._response_list = []  # List to store responses for reading

    def write(self, data: bytes) -> int:
        """Write data to the serial port."""
        if self._closed:
            raise OSError("Serial port closed")
        if self.write_error:
            raise IOError("Fake write error")
        self._write_count += 1
        # Generate response if configured - append the next response
        if self.responses:
            # Use a counter to track which response to return
            if not hasattr(self, '_response_counter'):
                self._response_counter = 0
            if self._response_counter < len(self.responses):
                self._response_list.append(self.responses[self._response_counter])
                self._response_counter += 1
                # Reset _response_offset for the new response
                self._response_offset = 0
        return len(data)

    def read(self, size: int) -> bytes:
        """Read data from the serial port."""
        if self._closed:
            return b""
        if self.raise_timeout:
            # Simulate timeout by always returning empty
            return b""
        # Read from response list - return from the last response added
        if not self._response_list:
            return b""
        response = self._response_list[-1]  # Use the last response
        # Return up to 'size' bytes from the current response
        remaining = len(response) - self._response_offset
        if remaining <= 0:
            # No more data in current response
            return b""
        data = response[self._response_offset:self._response_offset + size]
        self._response_offset += len(data)
        return data

    def reset_input_buffer(self):
        """Clear the input buffer."""
        self._input_buffer = io.BytesIO()

    def flush(self):
        """Flush the output buffer."""
        pass

    def close(self):
        """Close the serial port."""
        self._closed = True
        if hasattr(self._input_buffer, 'close'):
            self._input_buffer.close()
        if hasattr(self._output_buffer, 'close'):
            self._output_buffer.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False


class DiagnosticSession:
    """Manages a single diagnostic session with cleanup."""

    def __init__(self, output_dir: Path, verbose: bool = False):
        self.output_dir = output_dir
        self.verbose = verbose
        self.serial = None
        self.stop_event = False
        self._setup_output_files()

    def _setup_output_files(self):
        """Create timestamped output files."""
        timestamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        self.timestamp = timestamp
        # Create output directory
        self.output_dir.mkdir(parents=True, exist_ok=True)
        # Initialize output files
        self.requests_file = self.output_dir / f"requests_{timestamp}.csv"
        self.raw_log_file = self.output_dir / f"raw_serial_{timestamp}.log"
        self.decoded_file = self.output_dir / f"decoded_readbacks_{timestamp}.csv"
        self.active_file = self.output_dir / f"active_test_{timestamp}.csv"
        self.summary_file = self.output_dir / f"summary_{timestamp}.txt"
        # Write headers (append if file exists)
        with open(self.requests_file, "a", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                "request_id", "timestamp", "monotonic_ts", "motor", "request_hex",
                "bytes_written", "write_duration_ms", "response_start_ms", "response_complete_ms",
                "latency_ms", "response_length", "status", "error"
            ])
        with open(self.raw_log_file, "a") as f:
            f.write("# SMC3 Readback Diagnostic - Raw Serial Log\n")
            f.write(f"# Timestamp: {timestamp}\n")
            f.write("# Format: monotonic_ms,wall_ts,direction,request_id,hex_bytes\n")
        with open(self.decoded_file, "a", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                "request_id", "motor", "raw_response", "framing_valid",
                "feedback_raw", "target_raw", "feedback_decoded", "target_decoded",
                "decode_status", "payload_byte_1_raw", "payload_byte_2_raw"
            ])
        if self.active_file.exists():
            self.active_file.unlink()
        with open(self.active_file, "a", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                "step", "motor", "target", "transmitted_hex", "write_result",
                "readback_sample", "feedback_raw", "target_raw",
                "feedback_decoded", "target_decoded", "timestamp", "error",
                "decode_status", "payload_byte_1_raw", "payload_byte_2_raw"
            ])

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._cleanup()

    def _cleanup(self):
        """Ensure serial port is closed."""
        if self.serial and not self.serial._closed:
            try:
                self.serial.close()
            except Exception:
                pass
        # Also check diagnostic's serial if it exists
        if hasattr(self, '_diagnostic') and self._diagnostic and self._diagnostic.serial:
            if not self._diagnostic.serial._closed:
                try:
                    self._diagnostic.serial.close()
                except Exception:
                    pass

    def log_request(
        self,
        request_id: int,
        motor: str,
        request_bytes: bytes,
        written: int,
        write_duration_ms: float,
        response_start_ms: Optional[float],
        response_complete_ms: Optional[float],
        latency_ms: Optional[float],
        response_length: int,
        status: str,
        error: Optional[str] = None
    ):
        """Log a readback request."""
        now = dt.datetime.now().astimezone().isoformat(timespec="milliseconds")
        with open(self.requests_file, "a", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                request_id, now, request_id, motor, " ".join(f"{b:02X}" for b in request_bytes),
                str(written) if written is not None else "",
                f"{write_duration_ms:.3f}" if write_duration_ms is not None else "",
                f"{response_start_ms:.3f}" if response_start_ms is not None else "",
                f"{response_complete_ms:.3f}" if response_complete_ms is not None else "",
                f"{latency_ms:.3f}" if latency_ms is not None else "",
                str(response_length) if response_length is not None else "",
                status, error if error else ""
            ])

    def log_raw_serial(
        self,
        monotonic_ms: float,
        wall_ts: str,
        direction: str,
        request_id: Optional[int],
        hex_bytes: str
    ):
        """Log raw serial bytes."""
        with open(self.raw_log_file, "a") as f:
            f.write(f"{monotonic_ms:.3f},{wall_ts},{direction},{request_id},{hex_bytes}\n")

    def log_decoded(
        self,
        request_id: int,
        motor: str,
        raw_response: bytes,
        framing_valid: bool,
        feedback_raw: int,
        target_raw: int,
        feedback_decoded: Optional[float],
        target_decoded: Optional[float],
        decode_status: str,
        payload_byte_1_raw: int,
        payload_byte_2_raw: int
    ):
        """Log decoded readback data."""
        with open(self.decoded_file, "a", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                request_id, motor, " ".join(f"{b:02X}" for b in raw_response),
                str(framing_valid).lower(),
                feedback_raw, target_raw,
                f"{feedback_decoded}" if feedback_decoded is not None else "",
                f"{target_decoded}" if target_decoded is not None else "",
                decode_status,
                payload_byte_1_raw, payload_byte_2_raw
            ])

    def log_active_test(
        self,
        step: int,
        motor: str,
        target: int,
        transmitted_hex: str,
        write_result: int,
        readback_sample: int,
        feedback_raw: int,
        target_raw: int,
        feedback_decoded: Optional[float],
        target_decoded: Optional[float],
        timestamp: str,
        error: Optional[str] = None,
        decode_status: str = "",
        payload_byte_1_raw: int = 0,
        payload_byte_2_raw: int = 0
    ):
        """Log active test step."""
        with open(self.active_file, "a", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                step, motor, target, transmitted_hex, str(write_result),
                readback_sample, feedback_raw, target_raw,
                f"{feedback_decoded}" if feedback_decoded is not None else "",
                f"{target_decoded}" if target_decoded is not None else "",
                timestamp, error if error else "",
                decode_status, payload_byte_1_raw, payload_byte_2_raw
            ])

    def write_summary(self, stats: Dict[str, Any]):
        """Write human-readable summary."""
        with open(self.summary_file, "w") as f:
            f.write("=" * 70 + "\n")
            f.write("SMC3 READBACK DIAGNOSTIC SUMMARY\n")
            f.write("=" * 70 + "\n\n")
            f.write(f"Timestamp: {self.timestamp}\n")
            f.write(f"Output Directory: {self.output_dir}\n\n")
            f.write("SERIAL SETTINGS\n")
            f.write("-" * 70 + "\n")
            f.write(f"Port: {stats.get('port', 'N/A')}\n")
            f.write(f"Baud Rate: {stats.get('baud', 'N/A')}\n")
            f.write(f"Read Timeout: {stats.get('read_timeout', 'N/A')}\n")
            f.write(f"Write Timeout: {stats.get('write_timeout', 'N/A')}\n\n")
            f.write("TEST CONFIGURATION\n")
            f.write("-" * 70 + "\n")
            f.write(f"Mode: {stats.get('mode', 'N/A')}\n")
            f.write(f"Motors: {stats.get('motors', 'N/A')}\n")
            f.write(f"Duration: {stats.get('duration', 'N/A')}\n")
            f.write(f"Polling Rate: {stats.get('polling_rate', 'N/A')} Hz\n")
            f.write(f"Polling Interval: {stats.get('interval', 'N/A')}\n")
            f.write(f"Inter-request Delay: {stats.get('delay', 'N/A')}\n\n")
            f.write("STATISTICS\n")
            f.write("-" * 70 + "\n")
            f.write(f"Total Requests: {stats.get('total_requests', 0)}\n")
            f.write(f"Successful Responses: {stats.get('successful', 0)}\n")
            f.write(f"Timeouts: {stats.get('timeouts', 0)}\n")
            f.write(f"Malformed/Incomplete: {stats.get('malformed', 0)}\n")
            f.write(f"Errors: {stats.get('errors', 0)}\n\n")
            f.write("RESPONSE ANALYSIS\n")
            f.write("-" * 70 + "\n")
            f.write(f"Observed Response Lengths: {stats.get('response_lengths', 'N/A')}\n")
            f.write(f"Response Framing Pattern: {stats.get('framing', 'N/A')}\n")
            f.write(f"Value Ranges:\n")
            for motor in stats.get('value_ranges', {}):
                f.write(f"  Motor {motor}: {stats['value_ranges'][motor]}\n")
            f.write(f"Target Resolution: {stats.get('target_resolution', 'N/A')}\n")
            f.write(f"Feedback Resolution: {stats.get('feedback_resolution', 'N/A')}\n\n")
            f.write("LATENCY STATISTICS\n")
            f.write("-" * 70 + "\n")
            f.write(f"Mean Latency: {stats.get('mean_latency', 'N/A')}\n")
            f.write(f"Std Dev Latency: {stats.get('std_latency', 'N/A')}\n")
            f.write(f"Min Latency: {stats.get('min_latency', 'N/A')}\n")
            f.write(f"Max Latency: {stats.get('max_latency', 'N/A')}\n\n")
            f.write("UNEXPECTED DATA\n")
            f.write("-" * 70 + "\n")
            f.write(f"Unexpected Bytes: {stats.get('unexpected_bytes', 'None')}\n\n")
            f.write("CONCLUSIONS\n")
            f.write("-" * 70 + "\n")
            f.write(f"Response Format Established: {stats.get('format_established', 'N/A')}\n")
            f.write(f"Readback Sufficient for ±2-unit Verification: {stats.get('sufficient_for_settling', 'N/A')}\n\n")
            f.write("LIMITATIONS AND UNRESOLVED QUESTIONS\n")
            f.write("-" * 70 + "\n")
            f.write(f"Limitations: {stats.get('limitations', 'None')}\n")
            f.write(f"Unresolved: {stats.get('unresolved', 'None')}\n")
            f.write("\n" + "=" * 70 + "\n")


class ReadbackDiagnostic:
    """Main diagnostic engine."""

    def __init__(
        self,
        session: DiagnosticSession,
        serial,
        motor: str,
        verbose: bool = False
    ):
        self.session = session
        self.serial = serial
        self.motor = motor
        self.verbose = verbose
        self.request_counter = 0
        self.running = False
        self._init_stats()

    def _init_stats(self):
        """Initialize statistics tracking."""
        self.stats = {
            "total_requests": 0,
            "successful": 0,
            "timeouts": 0,
            "malformed": 0,
            "errors": 0,
            "response_lengths": set(),
            "value_ranges": {},
            "latencies": [],
            "unexpected_bytes": [],
            "format_established": False,
            "sufficient_for_settling": None,
            "limitations": [],
            "unresolved": []
        }
        self.last_response = b""  # Most recent response bytes from poll_motor()

    def send_request(self) -> Tuple[bytes, int]:
        """Send a readback request and return (response_bytes, bytes_written)."""
        request = READ_COMMANDS[self.motor]
        try:
            written = self.serial.write(request)
            if written != len(request):
                raise IOError(f"Short write: {written}/{len(request)}")
            self.serial.flush()
            return b"", written
        except Exception as e:
            raise e

    def read_response(self, timeout: float) -> bytes:
        """Read response with timeout."""
        start = time.monotonic()
        deadline = start + timeout
        response = bytearray()
        try:
            while time.monotonic() < deadline:
                chunk = self.serial.read(1)
                if not chunk:
                    time.sleep(0.001)
                    continue
                response.extend(chunk)
                # Log received bytes
                hex_str = " ".join(f"{b:02X}" for b in response)
                self.session.log_raw_serial(
                    monotonic_ms=time.monotonic() * 1000,
                    wall_ts=dt.datetime.now().astimezone().isoformat(timespec="milliseconds"),
                    direction="RX",
                    request_id=self.request_counter,
                    hex_bytes=hex_str
                )
        except Exception as e:
            raise e
        return bytes(response)

    def poll_motor(
        self,
        timeout: float,
        interval: float,
        delay: float = 0.0
    ) -> bool:
        """Poll a single motor and return True if response received."""
        self.last_response = b""
        self.request_counter += 1
        request_id = self.request_counter
        request = READ_COMMANDS[self.motor]
        start = time.monotonic()
        written = None
        response = b""
        error = None
        status = "TIMEOUT"
        response_start_ms = None
        response_complete_ms = None
        latency_ms = None
        response_length = 0  # Initialize to avoid UnboundLocalError

        try:
            # Send request
            written = self.serial.write(request)
            if written != len(request):
                error = f"Short write: {written}/{len(request)}"
                self.stats["errors"] += 1
                self.session.log_request(
                    request_id, self.motor, request, written,
                    (time.monotonic() - start) * 1000, None, None, None,
                    None, "ERROR", error
                )
                return False

            self.serial.flush()

            # Log TX
            hex_str = " ".join(f"{b:02X}" for b in request)
            self.session.log_raw_serial(
                monotonic_ms=start * 1000,
                wall_ts=dt.datetime.now().astimezone().isoformat(timespec="milliseconds"),
                direction="TX",
                request_id=request_id,
                hex_bytes=hex_str
            )

            # Wait for response
            response_start_ms = (time.monotonic() - start) * 1000
            deadline = start + timeout
            response = bytearray()

            while time.monotonic() < deadline:
                chunk = self.serial.read(1)
                if not chunk:
                    time.sleep(0.001)
                    continue
                response.extend(chunk)
                # Log received bytes
                hex_str = " ".join(f"{b:02X}" for b in response)
                self.session.log_raw_serial(
                    monotonic_ms=time.monotonic() * 1000,
                    wall_ts=dt.datetime.now().astimezone().isoformat(timespec="milliseconds"),
                    direction="RX",
                    request_id=request_id,
                    hex_bytes=hex_str
                )

            response_complete_ms = (time.monotonic() - start) * 1000
            latency_ms = response_complete_ms - response_start_ms
            response_length = len(response)

            # Analyze response
            status = "OK" if response else "TIMEOUT"
            self.stats["total_requests"] += 1
            if status == "OK":
                self.stats["successful"] += 1
                self.stats["response_lengths"].add(response_length)
                self._analyze_response(request_id, response)
            elif response:
                self.stats["malformed"] += 1
            else:
                self.stats["timeouts"] += 1

            # Log request
            self.session.log_request(
                request_id, self.motor, request, written,
                (time.monotonic() - start) * 1000, response_start_ms,
                response_complete_ms, latency_ms, response_length, status, error
            )

            self.last_response = bytes(response)
            return status == "OK"

        except Exception as e:
            self.stats["total_requests"] += 1
            error = f"{type(e).__name__}: {e}"
            # Use default values if not set
            response_start_ms = response_start_ms or 0.0
            response_complete_ms = response_complete_ms or 0.0
            latency_ms = latency_ms or 0.0
            response_length = response_length or 0
            self.stats["errors"] += 1
            self.session.log_request(
                request_id, self.motor, request, written,
                (time.monotonic() - start) * 1000, response_start_ms,
                response_complete_ms, latency_ms, response_length, "ERROR", error
            )
            return False

    def _analyze_response(self, request_id: int, response: bytes):
        """Analyze response for framing and decode if possible."""
        # Basic framing analysis
        framing = {
            "starts_with_91": response and response[0] == 91,
            "ends_with_93": response and response[-1] == 93,
            "has_motor_byte": len(response) > 1 and response[1] in (65, 66, 67),
            "length": len(response),
            "raw_hex": " ".join(f"{b:02X}" for b in response)
        }

        # Check for known patterns
        if response.startswith(b"[rd") and len(response) >= 5:
            framing["is_readback_response"] = True
        else:
            framing["is_readback_response"] = False

        # Validate SMC3 readback response format: [motor_byte payload_1 payload_2]
        # Format: 0x5B motor_id payload_1 payload_2 0x5D
        # Length must be 5, start byte 0x5B (91), end byte 0x5D (93)
        # Motor byte must match expected motor
        valid = (
            len(response) == 5
            and response[0] == 0x5B  # 91 = '['
            and response[4] == 0x5D  # 93 = ']'
            and response[1] in (0x41, 0x42, 0x43)  # 'A', 'B', 'C'
        )
        if valid:
            # Check motor identifier matches expected motor
            expected_motor_byte = ord(self.motor)
            if response[1] != expected_motor_byte:
                valid = False

        # Extract payload bytes only from fully validated responses
        if valid:
            payload_byte_1_raw = response[2]
            payload_byte_2_raw = response[3]
            feedback_raw = payload_byte_1_raw
            target_raw = payload_byte_2_raw
            feedback_decoded = feedback_raw * 4
            target_decoded = target_raw * 4
            decode_status = "OK"
        else:
            payload_byte_1_raw = 0
            payload_byte_2_raw = 0
            feedback_raw = 0
            target_raw = 0
            feedback_decoded = None
            target_decoded = None
            decode_status = "ERROR"

        # Store for later analysis
        self.stats["format_established"] = True
        self.session.log_decoded(
            request_id, self.motor, response,
            framing["starts_with_91"] and framing["ends_with_93"],
            feedback_raw, target_raw,
            feedback_decoded, target_decoded,
            decode_status,
            payload_byte_1_raw, payload_byte_2_raw
        )

        # Check for unexpected bytes
        if framing["is_readback_response"]:
            # Extract potential values
            if len(response) >= 7:
                # Look for potential position values
                pass

    def run_passive(
        self,
        duration: float,
        polling_rate: float,
        delay: float = 0.0
    ):
        """Run passive readback polling."""
        self.running = True
        interval = 1.0 / polling_rate if polling_rate > 0 else DEFAULT_POLL_INTERVAL
        self.stats["mode"] = "PASSIVE"
        self.stats["interval"] = interval
        self.stats["polling_rate"] = polling_rate
        self.stats["delay"] = delay

        print(f"\nStarting passive polling for {self.motor}...")
        print(f"Interval: {interval:.3f}s, Timeout: {DEFAULT_TIMEOUT}s")
        print(f"Press Ctrl+C to stop.\n")

        start = time.monotonic()
        last_poll = start

        while self.running:
            now = time.monotonic()
            if now - last_poll >= interval:
                self.poll_motor(DEFAULT_TIMEOUT, interval, delay)
                last_poll = now
            time.sleep(0.01)

            elapsed = now - start
            if duration > 0 and elapsed >= duration:
                break

        self.running = False

    def run_active(
        self,
        motor: str,
        targets: List[int],
        settling_delay: float = 0.5
    ):
        """Run active target-resolution test."""
        self.running = True
        self.motor = motor
        self.stats["mode"] = "ACTIVE"
        self.stats["targets"] = targets
        self.stats["settling_delay"] = settling_delay

        print(f"\nActive target-resolution test for motor {motor}")
        print(f"Targets: {targets}")
        print(f"Settling delay: {settling_delay}s")
        print(f"Press Ctrl+C to stop.\n")

        start = time.monotonic()
        step = 0

        for target in targets:
            if not self.running:
                break

            step += 1
            transmitted = READ_COMMANDS[self.motor]
            transmitted_hex = " ".join(f"{b:02X}" for b in transmitted)

            print(f"\nStep {step}: Sending motor {motor} target = {target}")
            print(f"Transmitting: {transmitted_hex}")

            # Send position command
            try:
                written = self.serial.write(transmitted)
                if written != len(transmitted):
                    raise IOError(f"Short write: {written}/{len(transmitted)}")
                self.serial.flush()
            except Exception as e:
                print(f"Failed to send: {e}")
                break

            # Wait for settling
            print(f"Settling for {settling_delay}s...")
            time.sleep(settling_delay)

            # Query readback
            print(f"Querying readback for {motor}...")
            success = self.poll_motor(DEFAULT_TIMEOUT, 0.05)

            if success:
                response_hex = " ".join(f"{b:02X}" for b in self.last_response)
                print(f"Response: {response_hex}")

                # Log active test
                # Extract payload bytes from response using same logic as _analyze_response()
                response = self.last_response
                if (
                    len(response) == 5
                    and response[0] == 0x5B
                    and response[4] == 0x5D
                    and response[1] in (0x41, 0x42, 0x43)
                    and response[1] == ord(self.motor)
                ):
                    payload_byte_1_raw = response[2]
                    payload_byte_2_raw = response[3]
                    feedback_raw = payload_byte_1_raw
                    target_raw = payload_byte_2_raw
                    feedback_decoded = feedback_raw * 4
                    target_decoded = target_raw * 4
                    decode_status = "OK"
                else:
                    payload_byte_1_raw = 0
                    payload_byte_2_raw = 0
                    feedback_raw = 0
                    target_raw = 0
                    feedback_decoded = None
                    target_decoded = None
                    decode_status = "ERROR"

                self.session.log_active_test(
                    step=step,
                    motor=self.motor,
                    target=target,
                    transmitted_hex=transmitted_hex,
                    write_result=written,
                    readback_sample=1,
                    feedback_raw=feedback_raw,
                    target_raw=target_raw,
                    feedback_decoded=feedback_decoded,
                    target_decoded=target_decoded,
                    timestamp=dt.datetime.now().astimezone().isoformat(timespec="milliseconds"),
                    decode_status=decode_status,
                    payload_byte_1_raw=payload_byte_1_raw,
                    payload_byte_2_raw=payload_byte_2_raw
                )
            else:
                print("No response received")

            if self.running:
                print("Waiting for next step...")
                time.sleep(settling_delay)

        self.running = False


def detect_serial_info() -> Dict[str, Any]:
    """Detect available serial devices without auto-selecting."""
    devices = {}
    try:
        import serial.tools.list_ports
        ports = serial.tools.list_ports.comports()
        for port in ports:
            devices[port.device] = {
                "description": port.description,
                "hwid": getattr(port, 'hwid', 'N/A'),
                "manufacturer": getattr(port, 'manufacturer', 'N/A')
            }
    except Exception:
        pass
    return devices


def parse_motor_arg(motors: str) -> List[str]:
    """Parse motor argument."""
    valid = set("ABC")
    result = []
    # Handle ALL as special case
    if motors == "ALL":
        return ["A", "B", "C"]
    for m in motors:
        if m in valid:
            result.append(m)
    return result


def main(argv=None, serial_factory=None):
    parser = argparse.ArgumentParser(
        description="SMC3 Readback Diagnostic Utility for DOF Reality H3",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  Passive test of motor A:
    python smc3_readback_diagnostic.py --port /dev/ttyUSB0 --motor A --duration 30

  Passive test of all motors:
    python smc3_readback_diagnostic.py --port /dev/ttyUSB0 --motor ALL --duration 60

  Active target-resolution test:
    python smc3_readback_diagnostic.py --port /dev/ttyUSB0 --active-target-test --motor A

  Passive test with custom polling rate:
    python smc3_readback_diagnostic.py --port /dev/ttyUSB0 --motor A --duration 30 --polling-rate 10

  Passive test with inter-request delay:
    python smc3_readback_diagnostic.py --port /dev/ttyUSB0 --motor A --duration 30 --delay 0.1

  Simulate mode (no hardware):
    python smc3_readback_diagnostic.py --simulate --simulate-response "5B 72 64 41 5D" --simulate-count 5 --motor A
"""
    )

    parser.add_argument(
        "--port",
        required=False,  # Not required if --list-devices is used
        help="Serial device path (e.g., /dev/ttyUSB0)"
    )
    parser.add_argument(
        "--baud",
        type=int,
        default=SMC3_BAUD,
        help=f"Baud rate (default: {SMC3_BAUD})"
    )
    parser.add_argument(
        "--motor",
        required=False,  # Not required if --list-devices is used
        choices=["A", "B", "C", "ALL"],
        help="Motor to poll: A, B, C, or ALL"
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=0,
        help="Duration in seconds (0 for unlimited)"
    )
    parser.add_argument(
        "--polling-rate",
        type=float,
        default=4.0,
        help="Polling rate in Hz (default: 4.0, interval ~0.25s)"
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.0,
        help="Delay between requests in seconds (default: 0)"
    )
    parser.add_argument(
        "--read-timeout",
        type=float,
        default=DEFAULT_TIMEOUT,
        help="Read timeout in seconds (default: 0.10)"
    )
    parser.add_argument(
        "--write-timeout",
        type=float,
        default=0.5,
        help="Write timeout in seconds (default: 0.5)"
    )
    parser.add_argument(
        "--active-target-test",
        action="store_true",
        help="Enable active target-resolution test"
    )
    parser.add_argument(
        "--active-motor",
        type=str,
        choices=["A", "B", "C"],
        help="Motor for active test (required with --active-target-test)"
    )
    parser.add_argument(
        "--active-settle",
        type=float,
        default=0.5,
        help="Settling delay for active test (default: 0.5)"
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=None,
        help="Output directory (default: timestamped subdir in cwd)"
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose raw-byte display"
    )
    parser.add_argument(
        "--list-devices",
        action="store_true",
        help="List detected serial devices and exit"
    )
    parser.add_argument(
        "--simulate",
        action="store_true",
        help="Enable simulation mode (uses FakeSerial, no hardware required)"
    )
    parser.add_argument(
        "--simulate-response",
        action="append",
        metavar="HEX",
        help="Canned response in hex format (repeatable, consumed in FIFO order)"
    )
    parser.add_argument(
        "--simulate-count",
        type=int,
        default=10,
        metavar="N",
        help="Number of requests to simulate before stopping (default: 10, 0=unlimited in passive mode)"
    )

    if argv is None:
        args = parser.parse_args()
    else:
        args = parser.parse_args(argv)

    # ── Simulate mode branch (early exit, before hardware-dependent code) ─
    if args.simulate:
        # Task 3.3: --port is optional in simulate mode
        sim_port = args.port if args.port else "/dev/null"
        sim_responses = [
            bytes(int(h, 16) for h in hex_str.split())
            for hex_str in (args.simulate_response or [])
        ]

        # Determine motors: use --motor if provided, else --active-motor, else default "A"
        if args.motor:
            motors = parse_motor_arg(args.motor)
        elif args.active_motor:
            motors = [args.active_motor]
        else:
            motors = ["A"]

        # Active test targets
        active_targets = ACTIVE_TEST_SEQUENCE[:]

        print("\n" + "=" * 70)
        print("SIMULATION MODE — no hardware connected")
        print("=" * 70)
        print(f"Port: {sim_port}")
        print(f"Baud: {args.baud}")
        print(f"Motors: {motors}")
        print(f"Mode: {'ACTIVE' if args.active_target_test else 'PASSIVE'}")
        if args.active_target_test:
            print(f"Active Test Motors: {args.active_motor}")
            print(f"Active Test Targets: {active_targets}")
            print(f"Settling Delay: {args.active_settle}s")
        else:
            print(f"Simulate Count: {args.simulate_count}")
            print(f"Polling Rate: {args.polling_rate} Hz")
        print(f"Read Timeout: {args.read_timeout}s")
        print(f"Write Timeout: {args.write_timeout}s")
        print(f"Canned Responses: {len(sim_responses)}")
        print("=" * 70 + "\n")

        # No-op DiagnosticSession subclass — overrides all file-writing methods
        class _SimulateSession(DiagnosticSession):
            """No-op DiagnosticSession for simulate mode.

            Overrides every method that would write CSV, raw, or summary files.
            This avoids modifying DiagnosticSession itself while ensuring
            zero disk I/O during simulation.
            """
            def _setup_output_files(self):
                pass  # no CSV or raw files in simulation
            def write_summary(self, stats):
                pass  # summary printed to stdout instead
            def log_request(self, *a, **kw):
                pass
            def log_raw_serial(self, *a, **kw):
                pass
            def log_decoded(self, *a, **kw):
                pass
            def log_active_test(self, *a, **kw):
                pass

        # Task 2.1: serial_factory producing FakeSerial (or injected factory for tests)
        def sim_factory(port=sim_port, baudrate=args.baud,
                        timeout=args.read_timeout, responses=sim_responses):
            if serial_factory is not None:
                return serial_factory(
                    port=port, baudrate=baudrate,
                    timeout=timeout, responses=responses
                )
            return FakeSerial(
                port=port, baudrate=baudrate,
                timeout=timeout, responses=responses
            )

        # Task 2.3: request counter stops at --simulate-count
        simulate_count = args.simulate_count  # 0 = unlimited in passive, fixed in active
        request_counter = [0]  # mutable container for closure

        def _request_limit_reached():
            if simulate_count == 0:
                return False
            return request_counter[0] >= simulate_count

        try:
            with _SimulateSession(Path("smc3_diagnostic_output"), verbose=args.verbose) as session:
                ser = sim_factory()
                session.serial = ser

                diagnostic = ReadbackDiagnostic(session, ser, args.motor if args.motor else args.active_motor, verbose=args.verbose)

                if args.active_target_test:
                    # Active-target-test mode: fixed sequence, --simulate-count limits steps
                    print("\nStarting active target-resolution test (SIMULATION)...")
                    targets = active_targets[:]
                    if simulate_count > 0:
                        targets = targets[:simulate_count]
                    diagnostic.run_active(args.active_motor, targets, args.active_settle)
                else:
                    # Passive mode: round-robin motor distribution for ALL
                    if args.motor == "ALL":
                        motor_cycle = ["A", "B", "C"]
                        print(f"\nStarting passive polling (SIMULATION) — round-robin motors...")
                        print(f"Simulate Count: {simulate_count}")
                        print(f"Polling Rate: {args.polling_rate} Hz")
                        interval = 1.0 / args.polling_rate if args.polling_rate > 0 else DEFAULT_POLL_INTERVAL
                        start = time.monotonic()
                        last_poll = start
                        motor_index = 0
                        # Use a shared stats dict across motor instances
                        diagnostic = ReadbackDiagnostic(session, ser, "A", verbose=args.verbose)
                        while not _request_limit_reached():
                            now = time.monotonic()
                            if now - last_poll >= interval:
                                motor = motor_cycle[motor_index % 3]
                                # Create fresh diagnostic for each motor to avoid
                                # READ_COMMANDS["ALL"] KeyError
                                diag_motor = ReadbackDiagnostic(
                                    session, ser, motor, verbose=args.verbose
                                )
                                # Merge stats from previous iteration
                                diag_motor.stats.update(diagnostic.stats)
                                diag_motor.request_counter = diagnostic.request_counter
                                request_counter[0] += 1
                                diag_motor.running = True
                                diag_motor.poll_motor(DEFAULT_TIMEOUT, interval, args.delay)
                                diagnostic = diag_motor
                                motor_index += 1
                                last_poll = now
                            time.sleep(0.01)
                        diagnostic.running = False
                    else:
                        # Non-ALL passive mode: single motor, respect simulate-count
                        print("\nStarting passive readback polling (SIMULATION)...")
                        interval = 1.0 / args.polling_rate if args.polling_rate > 0 else DEFAULT_POLL_INTERVAL
                        start = time.monotonic()
                        last_poll = start
                        diagnostic.running = True
                        while diagnostic.running and not _request_limit_reached():
                            now = time.monotonic()
                            if now - last_poll >= interval:
                                diagnostic.request_counter += 1
                                request_counter[0] += 1
                                diagnostic.poll_motor(DEFAULT_TIMEOUT, interval, args.delay)
                                last_poll = now
                            time.sleep(0.01)
                        diagnostic.running = False

                # Task 5.1: Print summary to stdout instead of file
                stats = diagnostic.stats
                stats["port"] = sim_port
                stats["baud"] = args.baud
                stats["read_timeout"] = args.read_timeout
                stats["write_timeout"] = args.write_timeout
                stats["mode"] = "SIMULATION_" + (args.active_target_test and "ACTIVE" or "PASSIVE")
                stats["motors"] = ",".join(motors)
                stats["duration"] = args.duration
                stats["polling_rate"] = args.polling_rate
                stats["interval"] = 1.0 / args.polling_rate
                stats["delay"] = args.delay
                stats["response_lengths"] = sorted(list(stats["response_lengths"]))
                stats["simulate_count"] = simulate_count
                stats["format_established"] = stats["format_established"]
                stats["sufficient_for_settling"] = "UNKNOWN - Simulation mode"
                stats["limitations"] = ["Simulation mode — no real hardware data"]
                stats["unresolved"] = ["Simulation mode — no real hardware data"]

                # Task 5.1, 5.2: Print summary to stdout
                print("\n" + "=" * 70)
                print("SIMULATION SUMMARY")
                print("=" * 70)
                print(f"Mode: SIMULATION")
                print(f"Total Requests: {stats['total_requests']}")
                print(f"Successful Responses: {stats['successful']}")
                print(f"Timeouts: {stats['timeouts']}")
                print(f"Malformed/Incomplete: {stats['malformed']}")
                print(f"Errors: {stats['errors']}")
                print(f"Motors: {stats['motors']}")
                print(f"Simulate Count: {stats['simulate_count']}")
                print("=" * 70)

                return 0

        except KeyboardInterrupt:
            print("\n\nInterrupted by user. Cleaning up...")
            return 130

        except Exception as e:
            print(f"\nError: {e}")
            import traceback
            if args.verbose:
                traceback.print_exc()
            return 1

    # List devices if requested
    if args.list_devices:
        print("\nDetected Serial Devices:")
        print("-" * 50)
        devices = detect_serial_info()
        if devices:
            for port, info in devices.items():
                print(f"{port}:")
                print(f"  Description: {info.get('description', 'N/A')}")
                print(f"  HWID: {info.get('hwid', 'N/A')}")
                print(f"  Manufacturer: {info.get('manufacturer', 'N/A')}")
        else:
            print("No serial devices detected.")
        return 0

    # Validate arguments
    if args.active_target_test:
        if not args.active_motor:
            parser.error("--active-target-test requires --active-motor")
        if args.motor != args.active_motor:
            print("Warning: --motor and --active-motor differ. Using --active-motor for active test.")

    # Parse motors (only if not listing devices)
    if not args.list_devices:
        motors = parse_motor_arg(args.motor)
        if not motors:
            parser.error("--motor must contain A, B, C, or ALL")

        # Validate polling rate
        if args.polling_rate <= 0:
            parser.error("--polling-rate must be > 0")

        # Validate active test targets
        active_targets = ACTIVE_TEST_SEQUENCE[:]

        # Create output directory
        if args.output_dir:
            output_dir = Path(args.output_dir)
        else:
            output_dir = Path("smc3_diagnostic_output")

    # ── Real-hardware branch (unchanged) ──────────────────────────────
    # Detect serial info
    devices = detect_serial_info()
    port_info = devices.get(args.port, {})

    print("\n" + "=" * 70)
    print("SMC3 READBACK DIAGNOSTIC UTILITY")
    print("=" * 70)
    print(f"Port: {args.port}")
    print(f"Baud: {args.baud}")
    print(f"Motors: {motors}")
    print(f"Mode: {'ACTIVE' if args.active_target_test else 'PASSIVE'}")
    if args.active_target_test:
        print(f"Active Test Motors: {args.active_motor}")
        print(f"Active Test Targets: {active_targets}")
        print(f"Settling Delay: {args.active_settle}s")
    else:
        print(f"Duration: {args.duration}s")
        print(f"Polling Rate: {args.polling_rate} Hz")
        print(f"Polling Interval: {1.0/args.polling_rate:.3f}s")
        print(f"Inter-request Delay: {args.delay}s")
    print(f"Read Timeout: {args.read_timeout}s")
    print(f"Write Timeout: {args.write_timeout}s")
    print(f"Output Directory: {output_dir}")

    if port_info:
        print(f"\nDetected Device Info:")
        print(f"  Description: {port_info.get('description', 'N/A')}")
        print(f"  HWID: {port_info.get('hwid', 'N/A')}")
        print(f"  Manufacturer: {port_info.get('manufacturer', 'N/A')}")

    print("\n" + "=" * 70)
    print("WARNING: This is a diagnostic tool.")
    if args.active_target_test:
        print("The active test will send position commands to the controller.")
        print("Ensure the platform is secured and the area is clear.")
        confirm = input("\nConfirm you understand and want to proceed? [y/N]: ").strip().lower()
        if confirm != 'y':
            print("Aborted by user.")
            return 0

    print("=" * 70 + "\n")

    # Create session and use as context manager
    try:
        with DiagnosticSession(output_dir, verbose=args.verbose) as session:
            # Open serial port
            print(f"Opening serial port: {args.port}")
            # Use real serial port for normal execution, or injected factory for tests
            factory = serial_factory or serial.Serial
            ser = factory(
                port=args.port,
                baudrate=args.baud,
                timeout=args.read_timeout,
                write_timeout=args.write_timeout
            )
            # Store serial in session for cleanup
            session.serial = ser

            # Create diagnostic engine
            diagnostic = ReadbackDiagnostic(session, ser, args.motor, verbose=args.verbose)

            # Run test
            if args.active_target_test:
                # Active test mode
                print("\nStarting active target-resolution test...")
                diagnostic.run_active(args.active_motor, active_targets, args.active_settle)
            else:
                # Passive test mode
                print("\nStarting passive readback polling...")
                diagnostic.run_passive(args.duration, args.polling_rate, args.delay)

            # Write summary
            stats = diagnostic.stats
            stats["port"] = args.port
            stats["baud"] = args.baud
            stats["read_timeout"] = args.read_timeout
            stats["write_timeout"] = args.write_timeout
            stats["mode"] = args.active_target_test and "ACTIVE" or "PASSIVE"
            stats["motors"] = ",".join(motors)
            stats["duration"] = args.duration
            stats["polling_rate"] = args.polling_rate
            stats["interval"] = 1.0 / args.polling_rate
            stats["delay"] = args.delay
            stats["response_lengths"] = sorted(list(stats["response_lengths"]))
            stats["format_established"] = stats["format_established"]
            stats["sufficient_for_settling"] = "UNKNOWN - No valid readback data"
            stats["limitations"] = [
                "Response format not conclusively established from raw data",
                "Resolution analysis pending actual controller data",
                "±2-unit settling verification cannot be determined without valid readback"
            ]
            stats["unresolved"] = [
                "Exact response framing unknown",
                "Position encoding (binary vs ASCII) unknown",
                "Scaling factors unknown",
                "Effective resolution unknown"
            ]

            session.write_summary(stats)

            print("\n" + "=" * 70)
            print("DIAGNOSTIC COMPLETE")
            print("=" * 70)
            print(f"Total Requests: {stats['total_requests']}")
            print(f"Successful: {stats['successful']}")
            print(f"Timeouts: {stats['timeouts']}")
            print(f"Malformed: {stats['malformed']}")
            print(f"Errors: {stats['errors']}")
            print(f"Output Directory: {output_dir}")
            print("\nGenerated files:")
            for f in output_dir.iterdir():
                print(f"  {f.name}")

            return 0

    except KeyboardInterrupt:
        print("\n\nInterrupted by user. Cleaning up...")
        return 130

    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        if args.verbose:
            traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
