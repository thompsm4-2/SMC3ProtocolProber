# Design

## Context

The `smc3_readback_diagnostic.py` utility already contains a `FakeSerial` class (lines 66-153) and a `main()` function that accepts a `serial_factory` parameter for test injection. The test suite (`test_readback_diagnostic.py`) uses this mechanism to exercise the full CLI path. However, there is no public CLI flag to enable simulation mode — users must write Python code to inject `FakeSerial`.

The diagnostic runs in two modes: passive polling and active target-resolution testing. In both modes, the only hardware interaction is through the serial port.

## Goals / Non-Goals

**Goals:**
- Add `--simulate` flag that routes through `FakeSerial` without changing any existing class or function
- Add `--simulate-response` (repeatable) for canned response injection
- Add `--simulate-count` to limit simulated requests
- Skip hardware prompts and file I/O in simulate mode (use a no-op `DiagnosticSession` that does nothing in `_setup_output_files()` and `write_summary()`)
- Preserve all existing CLI flags and behavior when `--simulate` is not used

**Non-Goals:**
- Modifying `FakeSerial`, `DiagnosticSession`, or `ReadbackDiagnostic` classes
- Adding new dependencies
- Simulating WT901C sensor behavior (the diagnostic only exercises SMC3)
- Modifying `h3_characterize.py` or any other module
- Hardware-in-the-loop testing

## Decisions

| Decision | Rationale | Alternatives Considered |
|----------|-----------|------------------------|
| Use `serial_factory` injection pattern | Already exists in `main()`, used by tests; zero new code for the injection mechanism | Add `--simulate` that directly instantiates `FakeSerial` (duplication) |
| Parse `--simulate-response` as hex strings | Matches the existing hex format used throughout the diagnostic (e.g., `"5B 72 64 41 5D"`) | Parse as raw bytes via `--simulate-response-binary` (unnecessary complexity) |
| Skip output files in simulate mode via no-op `DiagnosticSession` | No hardware means no real data to log; prevents confusing artifacts; no class modifications needed | Write simulated data to files (misleading — not real hardware data) |
| Default `--simulate-count` of 10 as request counter | Prevents infinite loops in passive mode while allowing meaningful test runs; independent of `--duration` | No default (would require `--duration 0` or `--simulate-count` every time) |
| Place logic in `main()` argument handling | Minimal change scope; no new classes needed | Create a `SimulateMode` class (over-engineering for one flag) |
| Round-robin motor distribution for `--motor ALL` in simulate mode | Evenly distributes requests across motors A, B, C; avoids `KeyError` that exists in real-hardware code | Interleaved polling, per-motor sub-sessions |
| `--port` optional in simulate mode | No hardware to connect; no device detection needed | Require `--port /dev/null` (adds friction) |
| `--simulate-count 0` = unlimited in passive, full sequence in active | Passive mode has no natural stop; active mode has a fixed 7-step sequence | Uniform behavior across modes (loss of expressiveness) |

## Risks / Trade-offs

| Risk | Mitigation |
|------|------------|
| `FakeSerial` may not fully replicate real serial timing | Clearly documented as simulation-only; tests verify it matches `FakeSerial` behavior, not real hardware |
| Hex parsing errors could crash the CLI | Validate hex strings early in argument parsing; provide clear error message |
| `--simulate` + `--active-target-test` interaction | Skip confirmation prompt but still exercise the active test path with `FakeSerial` |
| Users may confuse simulation results with real data | Print warning header: "SIMULATION MODE — no hardware connected" |
| `--motor ALL` in simulate mode uses round-robin distribution; real-hardware `--motor ALL` has a pre-existing `KeyError` bug | Clearly document that simulation behavior differs from real-hardware behavior; do not fix the pre-existing bug in this change |
| Other `DiagnosticSession` methods may write CSV or raw records when called | Verify in simulation tests that no other methods write files; if they do, bypass them via the inline subclass without modifying the class |

## Migration Plan

This change is purely additive. No migration is needed:
- Existing CLI usage is unaffected
- Existing test suite continues to use `serial_factory` injection directly
- New `--simulate` flag is opt-in
- Simulation mode uses a no-op `DiagnosticSession`: `main()` creates an inline subclass that overrides `_setup_output_files()` and `write_summary()` as no-ops (no class modification); verify no other `DiagnosticSession` methods write files during simulation
- 6 new unit tests added to `test_readback_diagnostic.py`; no existing tests modified

## Open Questions

None. The approach reuses existing patterns (`serial_factory` injection, `FakeSerial`) and requires no architectural changes.
