#!/usr/bin/env python3
"""Fake serial implementation for testing h3_characterize.py without hardware."""

import io
import time
from typing import Callable, Optional, List, Tuple


class FakeSerial:
    """Fake serial port for testing."""

    def __init__(
        self,
        port: str = "/dev/ttyACM0",
        baudrate: int = 9600,
        timeout: float = 1.0,
        write_timeout: float = 1.0,
        responses: Optional[List[Tuple[bytes, bytes]]] = None,
        write_error: bool = False,
        read_timeout: bool = False,
    ):
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.write_timeout = write_timeout
        self.responses = responses or []
        self.write_error = write_error
        self.read_timeout = read_timeout
        self._input_buffer = io.BytesIO()
        self._output_buffer = io.BytesIO()
        self._write_count = 0

    def write(self, data: bytes) -> int:
        """Write data to the serial port."""
        self._write_count += 1
        if self.write_error:
            raise IOError("Fake write error")
        if self.responses and self._write_count <= len(self.responses):
            expected_response = self.responses[self._write_count - 1][0]
            self._output_buffer.write(expected_response)
        self._output_buffer.flush()
        return len(data)

    def read(self, size: int) -> bytes:
        """Read data from the serial port."""
        if self.read_timeout and self._output_buffer.tell() == 0:
            return b""
        if self._output_buffer.tell() == 0:
            return b""
        data = self._output_buffer.read(size)
        return data

    def reset_input_buffer(self):
        """Clear the input buffer."""
        self._input_buffer = io.BytesIO()

    def flush(self):
        """Flush the output buffer."""
        pass

    def close(self):
        """Close the serial port."""
        self._output_buffer.close()
        self._input_buffer.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


def create_response_sequence(
    version_response: Optional[bytes] = None,
    enable_response: bytes = b"",
    position_responses: Optional[List[bytes]] = None,
    readback_responses: Optional[List[Tuple[str, bytes]]] = None,
):
    """Create a sequence of responses for the fake serial."""
    responses = []
    if version_response is not None:
        responses.append(b"[ver]", version_response)
    if enable_response:
        responses.append(b"[ena]", enable_response)
    if position_responses:
        for pos in position_responses:
            responses.append(smc3_frame("C", pos))
    if readback_responses:
        for motor, resp in readback_responses:
            req = smc3_frame("r", 0)  # Just need a request marker
            responses.append(req, resp)
    return responses


def smc3_frame(motor: str, position: int) -> bytes:
    """Create an SMC3 position frame."""
    if motor not in "ABC":
        raise ValueError(f"invalid motor: {motor!r}")
    position = max(0, min(1023, position))
    return bytes([91, ord(motor), (position >> 8) & 255, position & 255, 93])


if __name__ == "__main__":
    import sys
    sys.path.insert(0, "/home/mathomp/Documents/Development/MotionSimProjects/h3_wt901c_characterization_v0.1")
    from h3_characterize import main

    # Test 1: Basic version request and enable
    print("Test 1: Basic version request and enable")
    try:
        h3 = FakeSerial(
            responses=[
                (b"[ver]", b"[ver]01005D"),  # Version 1.00
                (b"[ena]", b"[ena]OK5D"),
            ]
        )
        main(["--port", "/dev/ttyACM0", "--no-version", "--yes"])
        h3.close()
        print("Test 1: PASSED\n")
    except Exception as e:
        print(f"Test 1: FAILED - {e}\n")

    # Test 2: TX logging
    print("Test 2: TX logging")
    try:
        import tempfile
        import os
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.csv') as f:
            tx_log_file = f.name
        h3 = FakeSerial(responses=[])
        main([
            "--port", "/dev/ttyACM0",
            "--tx-log", tx_log_file,
            "--no-version",
            "--yes",
            "--motors", "C",
            "--step", "20",
            "--limit", "20"
        ])
        h3.close()
        with open(tx_log_file, 'r') as f:
            lines = f.readlines()
        print(f"TX log has {len(lines)} lines (including header)")
        os.unlink(tx_log_file)
        print("Test 2: PASSED\n")
    except Exception as e:
        print(f"Test 2: FAILED - {e}\n")

    # Test 3: Readback polling
    print("Test 3: Readback polling")
    try:
        h3 = FakeSerial(
            read_timeout=True,
            responses=[
                (b"[rda]", b"[rda]OK5D"),
                (b"[rdb]", b"[rdb]OK5D"),
                (b"[rdc]", b"[rdc]OK5D"),
            ]
        )
        main([
            "--port", "/dev/ttyACM0",
            "--readback",
            "--readback-motors", "ABC",
            "--no-version",
            "--yes",
            "--motors", "C",
            "--step", "20",
            "--limit", "20",
            "--settle", "0.1",
            "--measure", "0.1"
        ])
        h3.close()
        with open("smc3_readback.log", 'r') as f:
            lines = f.readlines()
        print(f"Readback log has {len(lines)} lines (including header)")
        os.unlink("smc3_readback.log")
        print("Test 3: PASSED\n")
    except Exception as e:
        print(f"Test 3: FAILED - {e}\n")

    # Test 4: Sweep sequence
    print("Test 4: Sweep sequence verification")
    try:
        h3 = FakeSerial(responses=[])
        main([
            "--port", "/dev/ttyACM0",
            "--no-version",
            "--yes",
            "--motors", "C",
            "--step", "20",
            "--limit", "100"
        ])
        h3.close()
        print("Test 4: PASSED (sweep completed)\n")
    except Exception as e:
        print(f"Test 4: FAILED - {e}\n")

    print("All tests completed.")
