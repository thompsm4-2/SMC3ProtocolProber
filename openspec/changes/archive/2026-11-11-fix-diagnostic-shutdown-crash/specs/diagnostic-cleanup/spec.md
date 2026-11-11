# Spec Delta

## Purpose

Defines the shutdown and resource cleanup behavior for `DiagnosticSession`, ensuring safe serial port closure without crashes regardless of whether the serial connection is already closed or never opened.

## ADDED Requirements

### Requirement: Cleanup must not crash when serial is already closed

The diagnostic SHALL check the serial port's open/closed state using the public `closed` attribute (as exposed by pySerial `serial.Serial`) before attempting to close it. If the serial connection is already closed, `_cleanup()` SHALL return without error.

#### Scenario: Cleanup succeeds when serial is already closed

- **GIVEN** a `DiagnosticSession` with `self.serial` set to a pySerial `Serial` object that has been closed
- **WHEN** `_cleanup()` is called
- **THEN** no `AttributeError` is raised and the method returns successfully

#### Scenario: Cleanup succeeds when serial is None

- **GIVEN** a `DiagnosticSession` with `self.serial` set to `None`
- **WHEN** `_cleanup()` is called
- **THEN** no `AttributeError` is raised and the method returns successfully

#### Scenario: Cleanup closes an open serial port

- **GIVEN** a `DiagnosticSession` with `self.serial` set to an open pySerial `Serial` object
- **WHEN** `_cleanup()` is called
- **THEN** `self.serial.close()` is called and the serial port is closed

### Requirement: Cleanup must not crash on close errors

When `self.serial.close()` raises an exception, `_cleanup()` SHALL catch it and return without propagating the error.

#### Scenario: Close error is silently handled

- **GIVEN** a `DiagnosticSession` with `self.serial` set to a serial object whose `close()` method raises an exception
- **WHEN** `_cleanup()` is called
- **THEN** the exception is caught and `_cleanup()` returns without propagating the error

### Requirement: Cleanup of diagnostic's serial reference

When `self._diagnostic` exists and has a `serial` attribute, `_cleanup()` SHALL also close the diagnostic's serial port using the same safe pattern (public `closed` attribute, exception handling).

#### Scenario: Diagnostic serial is closed if open

- **GIVEN** a `DiagnosticSession` with `self._diagnostic` set to a `ReadbackDiagnostic` that has an open serial port
- **WHEN** `_cleanup()` is called
- **THEN** the diagnostic's serial port is also closed

#### Scenario: Diagnostic serial is skipped if already closed

- **GIVEN** a `DiagnosticSession` with `self._diagnostic` set to a `ReadbackDiagnostic` whose serial port is already closed
- **WHEN** `_cleanup()` is called
- **THEN** no error is raised and the method returns successfully
