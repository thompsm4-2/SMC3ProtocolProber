#!/usr/bin/env python3
"""Regression test for READ_COMMANDS encoding in h3_characterize.py.

Verifies that readback commands use uppercase motor identifiers
([rdA], [rdB], [rdC]) as confirmed by the November 14, 2026
H3 readback investigation.

See BUG-001 and openspec/changes/fix-readback-encoding/.
"""

from src.calibration.h3_characterize import READ_COMMANDS


def test_read_commands_uppercase_encoding():
    """READ_COMMANDS must produce uppercase motor identifiers."""
    assert READ_COMMANDS["A"] == b"[rdA]", \
        f"Expected b'[rdA]', got {READ_COMMANDS['A']!r}"
    assert READ_COMMANDS["B"] == b"[rdB]", \
        f"Expected b'[rdB]', got {READ_COMMANDS['B']!r}"
    assert READ_COMMANDS["C"] == b"[rdC]", \
        f"Expected b'[rdC]', got {READ_COMMANDS['C']!r}"


def test_read_commands_no_lowercase_motor_byte():
    """Motor identifier byte (offset 3) must not be lowercase a/b/c."""
    for motor, cmd in READ_COMMANDS.items():
        assert len(cmd) == 5, f"{motor}: expected 5-byte command, got {len(cmd)}"
        assert cmd[0] == 0x5B, f"{motor}: expected start byte 0x5B, got 0x{cmd[0]:02X}"
        assert cmd[1] == 0x72, f"{motor}: expected 'r' at offset 1, got 0x{cmd[1]:02X}"
        assert cmd[2] == 0x64, f"{motor}: expected 'd' at offset 2, got 0x{cmd[2]:02X}"
        assert cmd[3] in (0x41, 0x42, 0x43), \
            f"{motor}: expected uppercase motor byte (0x41-0x43), got 0x{cmd[3]:02X}"
        assert cmd[4] == 0x5D, f"{motor}: expected end byte 0x5D, got 0x{cmd[4]:02X}"
