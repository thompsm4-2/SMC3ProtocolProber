# Tasks

## 1. Remove Obsolete Test

- [x] 1.1 Remove the failing `test_readback_poller()` function from `src/calibration/test_v04.py`
- [x] 1.2 Verify the test file runs without the removed test (other tests unaffected)

## 2. Add Context Manager Test

- [x] 2.1 Implement `test_context_manager_entry_exit()` that:
  - Creates a `FakeSerial` instance with minimal responses
  - Uses `ReadbackPoller` as a context manager (`with` statement)
  - Verifies CSV log file is created on entry with correct header
  - Calls `poll_motor()` with a single motor to generate one log entry
  - Verifies CSV log file is properly closed on exit
  - Cleans up the log file after test completion

- [x] 2.2 Verify the test passes with deterministic timing

## 3. Add Successful poll_motor() Test

- [x] 3.1 Implement `test_successful_poll_motor()` that:
  - Creates a `FakeSerial` instance with a valid response for motor A
  - Uses `ReadbackPoller` as a context manager
  - Calls `poll_motor("A")` with a valid requested position
  - Verifies the response is captured correctly in the log
  - Checks that status is "OK" and response_len matches expected length
  - Cleans up the log file after test completion

- [x] 3.2 Verify the test passes with the valid response

## 4. Add Timeout Test

- [x] 4.1 Implement `test_poll_motor_timeout()` that:
  - Creates a `FakeSerial` instance with no responses (empty buffer)
  - Uses `ReadbackPoller` as a context manager with a short timeout
  - Calls `poll_motor("A")` which will timeout waiting for response
  - Verifies status is "TIMEOUT" in the log
  - Checks that response_len is 0 when no data is received
  - Cleans up the log file after test completion

- [x] 4.2 Verify the test passes with timeout behavior

## 5. Add Deterministic Interval Test

- [x] 5.1 Implement `test_poll_due_interval()` that:
  - Creates a `FakeSerial` instance with responses for all three motors (A, B, C)
  - Uses `ReadbackPoller` with a short, deterministic interval (e.g., 0.01 seconds)
  - Calls `poll_due("ABC", positions)` immediately to verify it skips (interval not reached)
  - Waits for the interval using `time.sleep()` then calls `poll_due()` again
  - Verifies the second call executes polling and logs all three motors
  - Checks CSV log contains entries for A, B, and C in sequence
  - Cleans up the log file after test completion

- [x] 5.2 Verify the test passes with deterministic interval timing

## 6. Add Immediate Polling Test

- [x] 6.1 Implement `test_poll_now_immediate()` that:
  - Creates a `FakeSerial` instance with responses for all three motors (A, B, C)
  - Uses `ReadbackPoller` as a context manager
  - Calls `poll_now("ABC", positions)` to poll all motors immediately
  - Verifies `poll_motor()` is called for each motor in sequence (A, B, C)
  - Checks CSV log contains entries for all three motors
  - Verifies `next_poll` is updated after polling completes
  - Cleans up the log file after test completion

- [x] 6.2 Verify the test passes with immediate polling

## 7. Run New Tests

- [x] 7.1 Run the modified test suite to verify all five new tests pass
- [x] 7.2 Confirm no test failures or unexpected behavior

## 8. Regression Check

- [x] 8.1 Run the existing test suite to check for regressions in other tests
- [x] 8.2 Verify all other tests in `src/calibration/test_v04.py` still pass
