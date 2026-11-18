# Design

## Context

`FakeSerial` is a test mock that implements a subset of the `serial.Serial` interface for use in unit tests. It accepts a `baudrate` parameter in `__init__` (line 73) and stores it as `self.baudrate` (line 80), but no method in the class reads this attribute. The class only uses `port`, `timeout`, `responses`, `write_error`, and `raise_timeout` for its actual behavior.

Three test assertions in `test_readback_diagnostic.py` verify `fake_serial.baudrate == 500000`, but these are the only references to this attribute anywhere in the codebase.

## Goals / Non-Goals

**Goals:**
- Remove the unused `self.baudrate` attribute from `FakeSerial.__init__`.
- Update test assertions that check `fake_serial.baudrate` to remove those checks.
- Preserve the `baudrate` parameter in the `FakeSerial.__init__` signature for API compatibility with `serial.Serial`.

**Non-Goals:**
- Refactoring FakeSerial's parameter handling or constructor signature.
- Adding new FakeSerial features or attributes.
- Changing any production code behavior.
- Modifying `test_fake_serial.py` (its FakeSerial class is a separate copy and was not flagged in BUG-011).

## Decisions

### Decision: Remove only the attribute assignment, keep the parameter

**Choice:** Remove `self.baudrate = baudrate` (line 80) but keep `baudrate: int = 9600` in the `__init__` signature.

**Rationale:** The `baudrate` parameter exists to match the `serial.Serial` constructor signature, which FakeSerial is designed to substitute for. Removing the parameter would be a breaking change for any code that calls `FakeSerial(port=..., baudrate=...)`. Keeping the parameter while not storing it is the minimal, safest change.

**Alternatives considered:**
1. **Remove the parameter entirely:** Would break all call sites that pass `baudrate=...` to FakeSerial. Unnecessary for this P3 fix.
2. **Add a `@property` that raises NotImplementedError:** Adds complexity for no benefit.
3. **Keep the attribute:** Leaves dead code in place. The BUG-011 backlog explicitly flags this as a code quality issue.

### Decision: Remove test assertions rather than replace them

**Choice:** Remove the three `assert fake_serial.baudrate == 500000` assertions from `test_readback_diagnostic.py` (lines 704, 835, 1162).

**Rationale:** The tests still verify that FakeSerial was constructed with correct parameters via other assertions (port, timeout, responses). The baudrate assertion adds no additional verification value since the baudrate is not used by any FakeSerial behavior. Removing the assertion simplifies the test without reducing coverage of meaningful behavior.

**Alternatives considered:**
1. **Replace with factory-call verification:** Would require restructuring the test to spy on the serial_factory call arguments. Over-engineered for a P3 cleanup.
2. **Add a test-only `__getattr__` hook:** Adds complexity and fragility.

## Risks / Trade-offs

| Risk | Mitigation |
|------|-----------|
| Test failure if a test checks `hasattr(fake_serial, 'baudrate')` | No such test exists in the codebase (verified by grep). |
| External code that patches or extends FakeSerial expects `self.baudrate` | FakeSerial is an internal test class; no external consumers. |
| The `baudrate` parameter is still accepted but unused, which could confuse future developers | The parameter is documented by its presence in the `serial.Serial`-compatible signature; this is standard mock pattern. |

## Migration Plan

No migration needed. This is a code cleanup with no behavioral change. No configuration updates, no API changes visible to end users.

## Open Questions

None. The scope is clear: remove one attribute and update three test assertions.
