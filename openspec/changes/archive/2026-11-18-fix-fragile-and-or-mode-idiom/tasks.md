# Tasks

## 1. Replace fragile idiom

- [x] 1.1 Replace `args.active_target_test and "ACTIVE" or "PASSIVE"` with `"ACTIVE" if args.active_target_test else "PASSIVE"` at line 1355 in `src/calibration/smc3_readback_diagnostic.py`
- [x] 1.2 Replace `"SIMULATION_" + (args.active_target_test and "ACTIVE" or "PASSIVE")` with `"SIMULATION_" + ("ACTIVE" if args.active_target_test else "PASSIVE")` at line 1176 in `src/calibration/smc3_readback_diagnostic.py`
- [x] 1.3 Run `py_compile` on `src/calibration/smc3_readback_diagnostic.py` to verify syntax
- [x] 1.4 Run `pytest src/calibration/test_readback_diagnostic.py` and confirm all 73 tests pass
