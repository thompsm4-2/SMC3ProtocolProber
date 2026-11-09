#!/usr/bin/env python3
"""Test suite for h3_characterize.py v0.4."""

import sys
import os
import tempfile
import time

sys.path.insert(0, "/home/mathomp/Documents/Development/MotionSimProjects/h3_wt901c_characterization_v0.1")

from h3_characterize import (
    smc3_frame, 
    send_command, 
    request_version,
    READ_COMMANDS,
    TXLogger,
    ReadbackPoller,
    build_sweep,
    positions_for,
)


def test_smc3_frame():
    """Test SMC3 frame encoding."""
    print("Testing smc3_frame()...")
    
    # Test center position (512 = 0x0200)
    frame = smc3_frame("A", 512)
    assert frame == bytes([91, 65, 2, 0, 93]), f"Expected [A 02 00], got {frame!r}"
    print("  Center position: OK")
    
    # Test offset position (510 = 0x01FE)
    frame = smc3_frame("A", 510)
    assert frame == bytes([91, 65, 1, 254, 93]), f"Expected [A 01 FE], got {frame!r}"
    print("  Offset position (510): OK")
    
    # Test C 532 (532 = 0x0214)
    frame = smc3_frame("C", 532)
    assert frame == bytes([91, 67, 2, 20, 93]), f"Expected [C 02 14], got {frame!r}"
    print("  C 532: OK")
    
    # Test all motors
    for motor in "ABC":
        frame = smc3_frame(motor, 512)
        assert frame[1] == ord(motor), f"Motor {motor} frame incorrect"
    print("  All motors: OK")
    
    # Test min/max bounds
    frame = smc3_frame("A", 0)
    assert frame == bytes([91, 65, 0, 0, 93])
    print("  Min position (0): OK")
    
    frame = smc3_frame("A", 1023)
    assert frame == bytes([91, 65, 3, 255, 93])  # 1023 = 0x03FF
    print("  Max position (1023): OK")
    
    print("smc3_frame(): PASSED\n")


def test_read_commands():
    """Test SMC3 read command bytes."""
    print("Testing READ_COMMANDS...")
    
    assert READ_COMMANDS["A"] == bytes([91, 114, 100, 97, 93]), "Read A incorrect"
    assert READ_COMMANDS["B"] == bytes([91, 114, 100, 98, 93]), "Read B incorrect"
    assert READ_COMMANDS["C"] == bytes([91, 114, 100, 99, 93]), "Read C incorrect"
    
    # Verify they're 5 bytes
    for motor, cmd in READ_COMMANDS.items():
        assert len(cmd) == 5, f"Read command for {motor} is not 5 bytes"
    
    print("  All read commands: OK")
    print("READ_COMMANDS(): PASSED\n")


def test_build_sweep():
    """Test sweep generation."""
    print("Testing build_sweep()...")
    
    sweep = build_sweep(20, 100)
    offsets = [s[1] for s in sweep]
    
    expected = [
        -20, -40, -60, -80, -100,
        -80, -60, -40, -20, 0,
        20, 40, 60, 80, 100,
        80, 60, 40, 20, 0
    ]
    
    assert offsets == expected, f"Expected {expected}, got {offsets}"
    print(f"  Sweep sequence matches expected")
    print("build_sweep(): PASSED\n")


def test_positions_for():
    """Test position calculation."""
    print("Testing positions_for()...")
    
    positions = positions_for("A", 20)
    assert positions == (532, 512, 512), f"Expected (532, 512, 512), got {positions}"
    print("  Motor A +20: OK")
    
    positions = positions_for("C", -20)
    assert positions == (512, 512, 492), f"Expected (512, 512, 492), got {positions}"
    print("  Motor C -20: OK")
    
    print("positions_for(): PASSED\n")


class FakeSerial:
    """Simple fake serial for testing."""
    
    def __init__(self, responses=None, write_error=False):
        self.responses = responses or []
        self.write_error = write_error
        self.call_count = 0
        self.write_count = 0
        self.read_data = b""
        self._output_buffer = b""
        self._response_index = 0
    
    def write(self, data):
        self.write_count += 1
        if self.write_error:
            raise IOError("Fake write error")
        # Store response for later read
        if self._response_index < len(self.responses):
            self._output_buffer = self.responses[self._response_index]
            self._response_index += 1
        return len(data)
    
    def read(self, size):
        if self._output_buffer:
            result = self._output_buffer[:size]
            self._output_buffer = self._output_buffer[size:]
            return result
        return b""
    
    def reset_input_buffer(self):
        pass
    
    def flush(self):
        pass
    
    def close(self):
        pass


def test_tx_logger():
    """Test TX logger."""
    print("Testing TXLogger...")
    
    # Test file exists error
    existing_file = "/tmp/test_tx_logger_exists.csv"
    with open(existing_file, 'w') as f:
        f.write("existing")
    
    try:
        logger = TXLogger(existing_file)
        print("  Existing file check: FAILED (should have raised)")
    except FileExistsError as e:
        print("  Existing file check: OK")
    finally:
        if os.path.exists(existing_file):
            os.unlink(existing_file)
    
    # Test successful logging
    new_file = "/tmp/test_tx_logger_new.csv"
    with TXLogger(new_file) as logger:
        logger.log("POSITION", "C", 532, bytes([91, 67, 2, 20, 93]), 5, 5)
    
    with open(new_file, 'r') as f:
        lines = f.readlines()
    
    assert len(lines) == 2, f"Expected 2 lines, got {len(lines)}"
    assert "POSITION" in lines[1], "Missing POSITION in log"
    assert "C" in lines[1], "Missing motor in log"
    assert "532" in lines[1], "Missing position in log"
    print("  Logging: OK")
    
    os.unlink(new_file)
    print("TXLogger(): PASSED\n")


def test_full_integration():
    """Test full integration with fake serial."""
    print("Testing full integration...")
    
    # Simulate the sequence: version request, enable, center position
    responses = [
        (b"[ver]", b"[ver]01005D"),  # Version response
        (b"[ena]", b"[ena]OK5D"),     # Enable response
        (b"[A\x02\x00\x93]", b"[A\x02\x00\x93]"),  # Center position (no response needed)
    ]
    
    h3 = FakeSerial(responses=responses)
    
    try:
        # Test version request
        request_version(h3)
        print("  Version request: OK")
        
        # Test enable command
        send_command(h3, b"[ena]")
        print("  Enable command: OK")
        
        # Test position command
        send_command(h3, smc3_frame("C", 532))
        print("  Position command: OK")
        
    except Exception as e:
        print(f"  FAILED: {e}")
        raise
    finally:
        h3.close()
    
    print("Full integration: PASSED\n")


def test_context_manager_entry_exit():
    """Test ReadbackPoller context manager entry and exit."""
    print("Testing context manager entry/exit...")
    
    import csv
    
    # Create a FakeSerial with minimal responses
    h3 = FakeSerial(responses=[b"[rda]OK5D"])
    
    # Use ReadbackPoller as a context manager
    with ReadbackPoller(h3, "/tmp/test_context_manager.csv", timeout=0.1, interval=0.25) as poller:
        # Call poll_motor() directly for a single motor
        poller.poll_motor("A", 512)
    
    # Verify CSV log file was created with correct header
    assert os.path.exists("/tmp/test_context_manager.csv"), "CSV log file not created"
    
    with open("/tmp/test_context_manager.csv", 'r') as f:
        lines = f.readlines()
    
    # Check header row
    assert "timestamp" in lines[0], "Missing 'timestamp' in header"
    assert "elapsed_ms" in lines[0], "Missing 'elapsed_ms' in header"
    assert "motor" in lines[0], "Missing 'motor' in header"
    assert "requested_position" in lines[0], "Missing 'requested_position' in header"
    assert "request_hex" in lines[0], "Missing 'request_hex' in header"
    assert "response_hex" in lines[0], "Missing 'response_hex' in header"
    assert "response_len" in lines[0], "Missing 'response_len' in header"
    assert "response_time_ms" in lines[0], "Missing 'response_time_ms' in header"
    assert "status" in lines[0], "Missing 'status' in header"
    assert "error" in lines[0], "Missing 'error' in header"
    
    # Verify file is properly closed (can be reopened and read)
    with open("/tmp/test_context_manager.csv", 'r') as f:
        content = f.read()
    assert len(content) > 0, "CSV file is empty"
    
    # Cleanup
    os.unlink("/tmp/test_context_manager.csv")
    
    print("  Context manager entry/exit: OK")
    print("  CSV header verification: OK")
    print("  File closure verification: OK")
    print("Context manager entry/exit: PASSED\n")


def test_successful_poll_motor():
    """Test successful poll_motor() operation with valid response."""
    print("Testing successful poll_motor()...")
    
    import csv
    
    # Create FakeSerial with valid response for motor A
    h3 = FakeSerial(responses=[b"[rda]OK5D"])
    
    with ReadbackPoller(h3, "/tmp/test_successful_poll.csv", timeout=0.1, interval=0.25) as poller:
        poller.poll_motor("A", 512)
    
    # Verify response was captured correctly
    with open("/tmp/test_successful_poll.csv", 'r') as f:
        lines = f.readlines()
    
    # Should have header + 1 data line
    assert len(lines) == 2, f"Expected 2 lines, got {len(lines)}"
    
    # Check status is OK
    assert "OK" in lines[1], f"Status should be OK, got: {lines[1]}"
    
    # Check response_len matches expected (7 bytes: [rda]OK5D)
    # Column indices: 0=timestamp, 1=elapsed_ms, 2=motor, 3=requested_position, 
    #                 4=request_hex, 5=response_hex, 6=response_len, 7=response_time_ms, 8=status, 9=error
    response_len = lines[1].split(",")[6]
    # The response_hex is "5B 72 64 61 5D 4F 4B 35 44" which is 9 characters (7 bytes with spaces)
    # [ = 0x5B, r = 0x72, d = 0x64, a = 0x61, ] = 0x5D, O = 0x4F, K = 0x4B, 5 = 0x35, D = 0x44
    assert response_len == "9", f"Expected response_len=9 (hex string with spaces), got {response_len}"
    
    # Check response_hex matches expected
    response_hex = lines[1].split(",")[5]
    # [rda]OK5D in hex with spaces: 5B 72 64 61 5D 4F 4B 35 44
    assert response_hex == "5B 72 64 61 5D 4F 4B 35 44", f"Expected [rda]OK5D in hex, got {response_hex}"
    
    # Cleanup
    os.unlink("/tmp/test_successful_poll.csv")
    
    print("  Successful poll: OK")
    print("  Response captured: OK")
    print("Successful poll_motor(): PASSED\n")


def test_poll_motor_timeout():
    """Test poll_motor() timeout when no response is received."""
    print("Testing poll_motor() timeout...")
    
    # Create FakeSerial with no responses (empty buffer)
    h3 = FakeSerial(responses=[])
    
    with ReadbackPoller(h3, "/tmp/test_timeout.csv", timeout=0.05, interval=0.25) as poller:
        poller.poll_motor("A", 512)
    
    # Verify timeout behavior
    with open("/tmp/test_timeout.csv", 'r') as f:
        lines = f.readlines()
    
    # Should have header + 1 data line
    assert len(lines) == 2, f"Expected 2 lines, got {len(lines)}"
    
    # Check status is TIMEOUT
    assert "TIMEOUT" in lines[1], f"Status should be TIMEOUT, got: {lines[1]}"
    
    # Check response_len is 0
    response_len = lines[1].split(",")[6]
    assert response_len == "0", f"Expected response_len=0, got {response_len}"
    
    # Check response_hex is empty
    response_hex = lines[1].split(",")[5]
    assert response_hex == "", f"Expected empty response_hex, got {response_hex}"
    
    # Cleanup
    os.unlink("/tmp/test_timeout.csv")
    
    print("  Timeout behavior: OK")
    print("  Status verification: OK")
    print("Timeout test: PASSED\n")


def test_poll_due_interval():
    """Test poll_due() respects the polling interval with deterministic timing."""
    print("Testing poll_due() interval...")
    
    import time
    
    # Create FakeSerial with responses for all three motors
    # We need 6 responses: 3 for first poll, 3 for second poll
    responses = [
        b"[rda]OK5D",  # Motor A (poll 1)
        b"[rdb]OK5D",  # Motor B (poll 1)
        b"[rdc]OK5D",  # Motor C (poll 1)
        b"[rda]OK5D",  # Motor A (poll 2)
        b"[rdb]OK5D",  # Motor B (poll 2)
        b"[rdc]OK5D",  # Motor C (poll 2)
    ]
    h3 = FakeSerial(responses=responses)
    
    # Use a short, deterministic interval (0.01 seconds)
    interval = 0.01
    
    with ReadbackPoller(h3, "/tmp/test_interval.csv", timeout=0.1, interval=interval) as poller:
        # positions is a string where each character is a position value
        positions = "512512512"  # A=512, B=512, C=512
        
        # Call poll_due() immediately - should skip since interval not reached
        poller.poll_due("ABC", positions)
        
        # Call poll_due() again immediately - should still skip
        poller.poll_due("ABC", positions)
    
    # Verify only one set of entries (since we didn't wait for interval)
    with open("/tmp/test_interval.csv", 'r') as f:
        lines = f.readlines()
    
    # Should have header + 3 data lines (one for each motor, but only one poll)
    assert len(lines) == 4, f"Expected 4 lines, got {len(lines)}"
    
    # Cleanup
    os.unlink("/tmp/test_interval.csv")
    
    print("  Interval skip behavior: OK")
    print("Interval test (skip): PASSED\n")
    
    # Now test with interval elapsed
    responses = [
        b"[rda]OK5D",  # Motor A (poll 1)
        b"[rdb]OK5D",  # Motor B (poll 1)
        b"[rdc]OK5D",  # Motor C (poll 1)
        b"[rda]OK5D",  # Motor A (poll 2)
        b"[rdb]OK5D",  # Motor B (poll 2)
        b"[rdc]OK5D",  # Motor C (poll 2)
    ]
    h3 = FakeSerial(responses=responses)
    
    with ReadbackPoller(h3, "/tmp/test_interval2.csv", timeout=0.1, interval=interval) as poller:
        positions = "512512512"  # A=512, B=512, C=512
        
        # Call poll_due() immediately - should skip
        poller.poll_due("ABC", positions)
        
        # Wait for interval + small margin
        time.sleep(interval + 0.01)
        
        # Call poll_due() again - should execute now
        poller.poll_due("ABC", positions)
    
    # Verify all three motors were polled twice
    with open("/tmp/test_interval2.csv", 'r') as f:
        lines = f.readlines()
    
    # Should have header + 6 data lines (2 polls x 3 motors)
    assert len(lines) == 7, f"Expected 7 lines, got {len(lines)}"
    
    # Verify responses for all three motors in second poll
    # Check that lines 4, 5, 6 have OK status
    for i in range(4, 7):
        assert "OK" in lines[i], f"Line {i} should have OK status, got: {lines[i]}"
    
    # Cleanup
    os.unlink("/tmp/test_interval2.csv")
    
    print("  Interval elapsed behavior: OK")
    print("Interval test (after wait): PASSED\n")


def test_poll_now_immediate():
    """Test poll_now() immediate polling of all motors."""
    print("Testing poll_now() immediate polling...")
    
    import csv
    
    # Create FakeSerial with responses for all three motors
    responses = [
        b"[rda]OK5D",  # Motor A
        b"[rdb]OK5D",  # Motor B
        b"[rdc]OK5D",  # Motor C
    ]
    h3 = FakeSerial(responses=responses)
    
    with ReadbackPoller(h3, "/tmp/test_now.csv", timeout=0.1, interval=0.25) as poller:
        positions = "512512512"  # A=512, B=512, C=512
        poller.poll_now("ABC", positions)
    
    # Verify responses captured for all motors
    with open("/tmp/test_now.csv", 'r') as f:
        lines = f.readlines()
    
    # Should have header + 3 data lines
    assert len(lines) == 4, f"Expected 4 lines, got {len(lines)}"
    
    # Check all three motors logged
    motors_in_log = [line.split(",")[2] for line in lines[1:]]
    assert "A" in motors_in_log, "Motor A should be in log"
    assert "B" in motors_in_log, "Motor B should be in log"
    assert "C" in motors_in_log, "Motor C should be in log"
    
    # Cleanup
    os.unlink("/tmp/test_now.csv")
    
    print("  All motors polled: OK")
    print("  Responses captured: OK")
    print("Immediate polling test: PASSED\n")


def test_sweep_sequence():
    """Verify the exact sweep sequence."""
    print("Testing sweep sequence...")
    
    sweep = build_sweep(20, 100)
    offsets = [s[1] for s in sweep]
    
    expected = [
        -20, -40, -60, -80, -100,
        -80, -60, -40, -20, 0,
        20, 40, 60, 80, 100,
        80, 60, 40, 20, 0
    ]
    
    assert offsets == expected, f"Sequence mismatch:\nExpected: {expected}\nGot: {offsets}"
    print("  Sequence verified")
    print("Sweep sequence: PASSED\n")


def test_position_frames():
    """Verify exact position frame bytes."""
    print("Testing position frames...")
    
    # Test specific frames mentioned in the task
    frame = smc3_frame("C", 532)
    assert frame == bytes([91, 67, 2, 20, 93]), f"Expected [C 02 14], got {frame!r}"
    print("  C 532 -> [C 02 14]: OK")
    
    frame = smc3_frame("A", 512)
    assert frame == bytes([91, 65, 2, 0, 93]), f"Expected [A 02 00], got {frame!r}"
    print("  A 512 -> [A 02 00]: OK")
    
    frame = smc3_frame("A", 510)
    assert frame == bytes([91, 65, 1, 254, 93]), f"Expected [A 01 FE], got {frame!r}"
    print("  A 510 -> [A 01 FE]: OK")
    
    print("Position frames: PASSED\n")


def main():
    """Run all tests."""
    print("=" * 60)
    print("h3_characterize.py v0.4 Test Suite")
    print("=" * 60)
    print()
    
    try:
        test_smc3_frame()
        test_read_commands()
        test_build_sweep()
        test_positions_for()
        test_tx_logger()
        test_readback_poller()
        test_full_integration()
        test_sweep_sequence()
        test_position_frames()
        
        print("=" * 60)
        print("ALL TESTS PASSED")
        print("=" * 60)
        return 0
        
    except AssertionError as e:
        print(f"\nTEST FAILED: {e}")
        return 1
    except Exception as e:
        print(f"\nTEST ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
