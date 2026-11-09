# Design

## Context

See `proposal.md` for the motivation and scope. The failing `test_readback_poller()` test in `src/calibration/test_v04.py` needs to be replaced with comprehensive tests covering the synchronous `ReadbackPoller` implementation. The tests should use the existing `FakeSerial` implementation.

## Goals / Non-Goals

**Goals:**
- Replace the failing test with five new tests that cover the synchronous `ReadbackPoller` implementation
- Ensure tests cover context manager usage, polling operations, timeout behavior, and interval timing
- Use deterministic timing for reliable test execution
- Maintain compatibility with existing `FakeSerial` interface

**Non-Goals:**
- Modifying production code or `FakeSerial` implementation
- Adding new dependencies
- Hardware testing
- Modifying other tests or the seven approved baseline specifications

## Decisions

| Decision | Rationale | Alternatives Considered |
|----------|-----------|------------------------|
| Replace rather than augment | The existing test is failing due to API changes; replacement is cleaner than maintaining broken tests | Augment with additional tests while fixing the old one |
| Use deterministic timing | `time.sleep()` with precise intervals ensures predictable test behavior | Use `time.monotonic()` directly with `time.advance_mock()` |
| Use existing `FakeSerial` | No need to introduce new mock classes; existing implementation is sufficient | Create a new `FakeSerial2` class |
| Context manager pattern | Matches the production code's usage pattern in `h3_characterize.py` | Direct instantiation without context manager |

## Risks / Trade-offs

| Risk | Mitigation |
|------|-----------|
| Timing tests may be flaky on slow systems | Use deterministic `time.sleep()` calls with fixed durations |
| `FakeSerial` may not fully match real serial behavior | Tests only cover synchronous polling; real hardware behavior is out of scope |
| CSV file cleanup needed between tests | Each test explicitly creates and removes its log files |
