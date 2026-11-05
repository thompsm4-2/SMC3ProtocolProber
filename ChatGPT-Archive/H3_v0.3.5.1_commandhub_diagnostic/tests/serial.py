"""Tiny pyserial-compatible echo stub used for non-hardware tests."""
from __future__ import annotations

import time

class SerialException(Exception):
    pass

class Serial:
    instances = []
    def __init__(self, port, baudrate, timeout=0.5, write_timeout=0.5):
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.write_timeout = write_timeout
        self.writes = []
        self.closed = False
        Serial.instances.append(self)
    def write(self, data):
        if self.closed:
            raise SerialException("port closed")
        data = bytes(data)
        self.writes.append(data)
        return len(data)
    def read(self, size=1):
        return b""
    def reset_input_buffer(self):
        return None
    def close(self):
        self.closed = True
