# Tasks

## 1. Add timeout parameter to run_passive()

- [ ] 1.1 Add `timeout: float = DEFAULT_TIMEOUT` parameter to `ReadbackDiagnostic.run_passive()` signature and replace the hardcoded `DEFAULT_TIMEOUT` in its `self.poll_motor(DEFAULT_TIMEOUT, interval, delay)` call with `self.poll_motor(timeout, interval, delay)`; update the print statement to display `timeout` instead of `DEFAULT_TIMEOUT`

## 2. Add timeout parameter to run_active()

- [ ] 2.1 Add `timeout: float = DEFAULT_TIMEOUT` parameter to `ReadbackDiagnostic.run_active()` signature and replace both hardcoded `DEFAULT_TIMEOUT` calls to `self.poll_motor(DEFAULT_TIMEOUT, 0.05)` with `self.poll_motor(timeout, 0.05)`

## 3. Wire args.read_timeout through main() — real-hardware branch

- [ ] 3.1 In the real-hardware branch of `main()`, pass `args.read_timeout` as the `timeout` argument to `diagnostic.run_passive(args.duration, args.polling_rate, args.delay)` (single motor passive path)
- [ ] 3.2 In the real-hardware branch of `main()`, pass `args.read_timeout` as the `timeout` argument to `diagnostic.run_active(args.active_motor, active_targets, args.active_settle, sample_count=args.active_samples)` (active test path)
- [ ] 3.3 In the real-hardware ALL-motors loop, pass `args.read_timeout` to each `diag_motor.poll_motor(args.read_timeout, interval, args.delay)` call

## 4. Wire args.read_timeout through main() — simulate branch

- [ ] 4.1 In the simulate branch of `main()`, pass `args.read_timeout` to `diagnostic.run_passive(args.duration, args.polling_rate, args.delay)` (single motor passive path)
- [ ] 4.2 In the simulate branch of `main()`, pass `args.read_timeout` to `diagnostic.run_active(args.active_motor, targets, args.active_settle, sample_count=args.active_samples)` (active test path)
- [ ] 4.3 In the simulate ALL-motors loop, pass `args.read_timeout` to each `diag_motor.poll_motor(args.read_timeout, interval, args.delay)` call

## 5. Verify correctness

- [ ] 5.1 Run `python3 -m pytest test_readback_diagnostic.py -v --tb=short` and confirm all 73 tests that were passing before still pass (the pre-existing `test_all_motor_cli_execution` failure is unrelated)
- [ ] 5.2 Run `python3 -m py_compile smc3_readback_diagnostic.py` to confirm the file compiles cleanly
