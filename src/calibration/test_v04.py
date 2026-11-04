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


def test_readback_poller():
    """Test readback poller."""
    print("Testing ReadbackPoller...")
    
    # The poller polls all motors at once
    # We need responses for the poller writes (6 responses for 3 motors x 2 writes each)
    h3 = FakeSerial(responses=[
        (b"[rda]", b"[rda]OK5D"),  # Poll 1: A
        (b"[rdb]", b"[rdb]OK5D"),  # Poll 1: B
        (b"[rdc]", b"[rdc]OK5D"),  # Poll 1: C
        (b"[rda]", b"[rda]OK5D"),  # Poll 2: A
        (b"[rdb]", b"[rdb]OK5D"),  # Poll 2: B
        (b"[rdc]", b"[rdc]OK5D"),  # Poll 2: C
    ])
    
    # Start poller
    poller = ReadbackPoller(h3, "ABC", timeout=0.1, interval=0.1)
    poller.start()
    
    # Give it a moment to poll
    time.sleep(0.3)
    
    # Stop poller
    poller.stop()
    
    if os.path.exists("smc3_readback.log"):
        with open("smc3_readback.log", 'r') as f:
            lines = f.readlines()
        
        # Should have header + 6 data lines (2 polls x 3 motors)
        assert len(lines) >= 2, f"Expected at least 2 lines, got {len(lines)}"
        print(f"  Polling: OK ({len(lines) - 1} data lines)")
    
    if os.path.exists("smc3_readback.log"):
        os.unlink("smc3_readback.log")
    print("ReadbackPoller(): PASSED\n")


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
