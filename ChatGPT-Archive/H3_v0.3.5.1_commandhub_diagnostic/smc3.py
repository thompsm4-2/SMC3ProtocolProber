"""SMC3 serial transport and CommandHub for the DOF Reality H3.

The command path intentionally follows the proven smc3util model:
MotorCommand -> CommandHub -> SerialTransport -> pyserial.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import threading
import time
from typing import Callable

import serial

BAUD_RATE = 500_000
MIN_POSITION = 0
MAX_POSITION = 1023
CENTER_POSITION = 512
MOTORS = ("A", "B", "C")


def _clamp_position(position: int) -> int:
    """Return an integer position constrained to the SMC3 range."""
    return max(MIN_POSITION, min(MAX_POSITION, int(position)))


def encode_command(motor: str, position: int) -> bytes:
    motor = str(motor).upper()
    if motor not in MOTORS:
        raise ValueError(f"Invalid motor: {motor!r}")
    position = _clamp_position(position)
    return bytes((0x5B, ord(motor), (position >> 8) & 0xFF, position & 0xFF, 0x5D))


def encode_enable() -> bytes:
    return b"[ena]"


def encode_disable() -> bytes:
    return b"[]"


def encode_version_request() -> bytes:
    return b"[ver]"


def encode_read_feedback(motor: str) -> bytes:
    motor = str(motor).upper()
    if motor not in MOTORS:
        raise ValueError(f"Invalid motor: {motor!r}")
    return bytes((0x5B, ord("r"), ord("d"), ord(motor), 0x5D))


@dataclass(frozen=True)
class MotorCommand:
    motor: str
    position: int

    def __post_init__(self) -> None:
        motor = str(self.motor).upper()
        if motor not in MOTORS:
            raise ValueError(f"Invalid motor: {self.motor!r}")
        try:
            position = int(self.position)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Invalid position: {self.position!r}") from exc
        object.__setattr__(self, "motor", motor)
        object.__setattr__(self, "position", _clamp_position(position))

    def frame(self) -> bytes:
        return encode_command(self.motor, self.position)


class SerialTransport:
    """Thin pyserial wrapper. It owns the serial connection and writes bytes."""

    def __init__(self, port: str, baud_rate: int = BAUD_RATE, debug: bool = False,
                 event: Callable[[str], None] | None = None) -> None:
        self.port = port
        self.baud_rate = baud_rate
        self.debug = debug
        self._event = event or (lambda _message: None)
        self._serial = None
        self._write_lock = threading.Lock()

    def open(self) -> None:
        if self._serial is not None:
            return
        self._serial = serial.Serial(
            self.port, self.baud_rate, timeout=0.5, write_timeout=0.5
        )
        time.sleep(2.0)

    def write(self, data: bytes) -> None:
        if self._serial is None:
            raise RuntimeError("Serial transport is not open")
        with self._write_lock:
            self._serial.write(data)
            if self.debug:
                self._event(f"TX {self._format_frame(data)}")

    def close(self) -> None:
        ser, self._serial = self._serial, None
        if ser is not None:
            ser.close()

    @staticmethod
    def _format_frame(data: bytes) -> str:
        if len(data) == 5 and data[0] == 0x5B and data[4] == 0x5D:
            return f"[{chr(data[1]) if 32 <= data[1] < 127 else '.'}..] | " + " ".join(f"{b:02X}" for b in data)
        return "".join(f"{b:02X}" for b in data)


class MotionCommandQueue:
    """Hybrid queue: latest value wins per motor, FIFO across motor slots."""

    def __init__(self) -> None:
        self._condition = threading.Condition()
        self._latest_by_motor: dict[str, MotorCommand] = {}
        self._order: deque[str] = deque()

    def put(self, command: MotorCommand) -> None:
        with self._condition:
            if command.motor not in self._latest_by_motor:
                self._order.append(command.motor)
            self._latest_by_motor[command.motor] = command
            self._condition.notify()

    def get(self, timeout: float | None = None) -> MotorCommand | None:
        with self._condition:
            if not self._order:
                if not self._condition.wait(timeout):
                    return None
            if not self._order:
                return None
            motor = self._order.popleft()
            return self._latest_by_motor.pop(motor)

    def empty(self) -> bool:
        with self._condition:
            return not self._order


class CommandHub:
    """Single worker dispatching control commands and motor commands."""

    def __init__(self, transport: SerialTransport, rate_hz: float = 30.0,
                 debug: bool = False, event: Callable[[str], None] | None = None) -> None:
        self.transport = transport
        self.rate_hz = float(rate_hz)
        self.debug = debug
        self._event = event or (lambda _message: None)
        self._control_queue: deque[bytes] = deque()
        self._control_condition = threading.Condition()
        self._motion_queue = MotionCommandQueue()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._tx_count = 0
        self._last_error: Exception | None = None

    @property
    def is_alive(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    @property
    def tx_count(self) -> int:
        return self._tx_count

    @property
    def last_error(self) -> Exception | None:
        return self._last_error

    def start(self) -> None:
        if self.is_alive:
            return
        self.transport.open()
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._worker_loop, name="smc3-commandhub", daemon=True)
        self._thread.start()

    def submit(self, command: MotorCommand) -> None:
        if not self.is_alive:
            raise RuntimeError("CommandHub is not running")
        self._motion_queue.put(command)

    def submit_control(self, frame: bytes) -> None:
        if not self.is_alive:
            raise RuntimeError("CommandHub is not running")
        with self._control_condition:
            self._control_queue.append(frame)
            self._control_condition.notify()

    def _get_control(self) -> bytes | None:
        with self._control_condition:
            if self._control_queue:
                return self._control_queue.popleft()
        return None

    def _worker_loop(self) -> None:
        interval = 1.0 / self.rate_hz if self.rate_hz > 0 else 0.0
        next_send = 0.0
        while not self._stop_event.is_set():
            frame = self._get_control()
            if frame is None:
                command = self._motion_queue.get(timeout=0.05)
                if command is None:
                    continue
                frame = command.frame()
            now = time.monotonic()
            if now < next_send:
                time.sleep(next_send - now)
            try:
                self.transport.write(frame)
                self._tx_count += 1
                next_send = time.monotonic() + interval
            except Exception as exc:  # surfaced through status; worker remains observable
                self._last_error = exc
                self._event(f"ERROR TX: {exc}")
                time.sleep(0.05)

    def stop(self) -> None:
        self._stop_event.set()
        with self._control_condition:
            self._control_condition.notify_all()
        thread = self._thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=1.0)
        self._thread = None
        self.transport.close()


class SMC3Transport:
    """Public transport facade used by the H3 driver and manual CLI."""

    def __init__(self, port: str, debug: bool = False,
                 event: Callable[[str], None] | None = None) -> None:
        self._events: deque[str] = deque()
        self._external_event = event
        self._state = (CENTER_POSITION, CENTER_POSITION, CENTER_POSITION)
        self.transport = SerialTransport(port, debug=debug, event=self._record_event)
        self.hub = CommandHub(self.transport, debug=debug, event=self._record_event)

    def _record_event(self, message: str) -> None:
        self._events.append(message)
        if self._external_event is not None:
            self._external_event(message)

    def start(self) -> None:
        self.hub.start()

    def thread_status(self) -> str:
        return f"writer={'alive' if self.hub.is_alive else 'stopped'}"

    def pop_events(self) -> list[str]:
        events = list(self._events)
        self._events.clear()
        return events

    def set_motor(self, motor: str, position: int) -> None:
        command = MotorCommand(motor, position)
        values = list(self._state)
        values["ABC".index(command.motor)] = command.position
        self.set_positions(*values)

    def set_positions(self, a: int, b: int, c: int) -> None:
        self._state = (_clamp_position(a), _clamp_position(b), _clamp_position(c))
        for motor, position in zip(MOTORS, self._state):
            self.hub.submit(MotorCommand(motor, position))

    def enable(self) -> None:
        self.hub.submit_control(encode_enable())

    def stop(self) -> None:
        self.hub.submit_control(encode_disable())

    def version(self) -> None:
        self.hub.submit_control(encode_version_request())

    def request_version(self) -> None:
        self.version()

    def status(self) -> str:
        error = self.hub.last_error
        error_text = "none" if error is None else repr(error)
        return f"TX frames: {self.hub.tx_count}; {self.thread_status()}; last error: {error_text}"

    def wait_for_idle(self, timeout: float = 1.0) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.hub._motion_queue.empty() and not self.hub._control_queue:
                return True
            time.sleep(0.005)
        return False

    def close(self) -> None:
        self.hub.stop()
