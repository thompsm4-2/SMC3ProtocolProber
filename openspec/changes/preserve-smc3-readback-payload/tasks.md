# Tasks

## 1. Inspect existing code and CSV consumers

- [ ] 1.1 Read `smc3_readback_diagnostic.py` lines 557-588 to understand the current `_analyze_response()` implementation and confirm it writes zeros to `feedback_raw` and `target_raw`
- [ ] 1.2 Read `smc3_readback_diagnostic.py` lines 186-202 to confirm the current CSV headers for `decoded_readbacks_*.csv` and `active_test_*.csv`
- [ ] 1.3 Search the codebase for external CSV readers of `decoded_readbacks` and `active_test` files to confirm no consumers would be broken by adding columns
- [ ] 1.4 Read `test_readback_diagnostic.py` to understand existing test conventions, FakeSerial behavior, and fixture patterns

## 2. Update CSV headers

- [ ] 2.1 Add `feedback_decoded`, `target_decoded`, `payload_byte_1_raw`, and `payload_byte_2_raw` to the decoded CSV header in `_setup_output_files()` (line ~189-193)
- [ ] 2.2 Add `feedback_decoded`, `target_decoded`, `payload_byte_1_raw`, and `payload_byte_2_raw` to the active test CSV header in `_setup_output_files()` (line ~198-202)
- [ ] 2.3 Update `log_decoded()` method signature and CSV writer call to accept and write the new fields (lines 266-288)
- [ ] 2.4 Update `log_active_test()` method signature and CSV writer call to accept and write the new fields (lines 290-314)
- [ ] 2.5 Verify Python syntax: `python -c "import py_compile; py_compile.compile('src/calibration/smc3_readback_diagnostic.py', doraise=True)"`

## 3. Update `_analyze_response()` to extract, scale, and map payload bytes

- [ ] 3.1 Modify `_analyze_response()` to extract `response[2]` as `payload_byte_1_raw` and `response[3]` as `payload_byte_2_raw` when the response is a validated five-byte readback response
- [ ] 3.2 Assign `feedback_raw = payload_byte_1_raw` and `target_raw = payload_byte_2_raw` (raw byte values in the 0–255 range)
- [ ] 3.3 Compute `feedback_decoded = feedback_raw * 4` and `target_decoded = target_raw * 4` (quantized position values, 0–1020 in increments of 4)
- [ ] 3.4 Set `decode_status` to `"OK"` for valid responses and `"ERROR"` for invalid responses
- [ ] 3.5 Verify the call to `session.log_decoded()` at line 576-580 is updated to pass the new fields
- [ ] 3.6 Verify Python syntax: `python -c "import py_compile; py_compile.compile('src/calibration/smc3_readback_diagnostic.py', doraise=True)"`

## 4. Update active test logging

- [ ] 4.1 Update the `log_active_test()` call in `run_active()` (line 678-690) to pass `payload_byte_1_raw`, `payload_byte_2_raw`, `feedback_raw`, `target_raw`, `feedback_decoded`, `target_decoded`, and `decode_status` values (extracted from the response using the same logic as `_analyze_response()`)
- [ ] 4.2 Verify Python syntax: `python -c "import py_compile; py_compile.compile('src/calibration/smc3_readback_diagnostic.py', doraise=True)"`

## 5. Add focused regression tests

- [ ] 5.1 Test: response `5B 41 7E 80 5D` — verify `payload_byte_1_raw=126`, `payload_byte_2_raw=128`, `feedback_raw=126`, `target_raw=128`, `feedback_decoded=504`, `target_decoded=512`, `decode_status="OK"`
- [ ] 5.2 Test: response `5B 41 00 00 5D` — verify `payload_byte_1_raw=0`, `payload_byte_2_raw=0`, `feedback_raw=0`, `target_raw=0`, `feedback_decoded=0`, `target_decoded=0`, `decode_status="OK"`
- [ ] 5.3 Test: response `5B 41 FF FF 5D` — verify `payload_byte_1_raw=255`, `payload_byte_2_raw=255`, `feedback_raw=255`, `target_raw=255`, `feedback_decoded=1020`, `target_decoded=1020`, `decode_status="OK"`
- [ ] 5.4 Test: response `5B 42 64 C8 5D` (Motor B) — verify `payload_byte_1_raw=100`, `payload_byte_2_raw=200`, `feedback_raw=100`, `target_raw=200`, `feedback_decoded=400`, `target_decoded=800`, `decode_status="OK"`
- [ ] 5.5 Test: response `5B 43 40 C0 5D` (Motor C) — verify `payload_byte_1_raw=64`, `payload_byte_2_raw=192`, `feedback_raw=64`, `target_raw=192`, `feedback_decoded=256`, `target_decoded=768`, `decode_status="OK"`
- [ ] 5.6 Test: invalid framing (e.g., 4-byte response `5B 41 7E 5D`) — verify `decode_status="ERROR"` and payload fields not populated
- [ ] 5.7 Test: wrong motor identifier (e.g., motor B response when requesting motor A) — verify `decode_status="ERROR"` and payload fields not populated
- [ ] 5.8 Test: verify `raw_response` is `"5B 41 7E 80 5D"` for the standard test response
- [ ] 5.9 Test: verify `framing_valid` is `"true"` for valid responses and `"false"` for invalid ones
- [ ] 5.10 Test: verify CSV headers contain `feedback_decoded`, `target_decoded`, `payload_byte_1_raw`, and `payload_byte_2_raw` columns

## 6. Run existing test suites

- [ ] 6.1 Run the complete `test_readback_diagnostic.py` suite and verify all existing tests pass
- [ ] 6.2 Run any directly affected CSV consumer tests (none identified, but verify no failures)
- [ ] 6.3 Run simulation-mode regression tests to confirm no behavioral changes
- [ ] 6.4 Report exact commands and results; stop if any test fails
