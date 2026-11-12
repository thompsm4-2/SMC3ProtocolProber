# Tasks

## 1. Update `DiagnosticSession._setup_output_files` to create timestamped subdirectory

- [x] 1.1 Add a run-start timestamp using `%Y-%m-%d_%H-%M-%S` format and generate the subdirectory name inside `_setup_output_files`, before creating files
- [x] 1.2 Create the timestamped subdirectory inside `self.output_dir` using `mkdir(parents=True, exist_ok=True)`, and update `self.output_dir` to point to the subdirectory
- [x] 1.3 Keep the existing file-level timestamp (`%Y%m%d_%H%M%S`) generation unchanged — derive both timestamps from the same `datetime.now()` call
- [x] 1.4 Verify: run the diagnostic with `--simulate` and confirm no directories are created (existing behavior preserved)

## 2. Update `DiagnosticSession._cleanup` and summary output

- [x] 2.1 Update `write_summary` to reference the (now subdirectory) `self.output_dir` — no code change needed since it already uses `self.output_dir`
- [x] 2.2 Update the end-of-run file listing (line 1282, `for f in output_dir.iterdir()`) to list files within the subdirectory instead of the parent
- [x] 2.3 Update the end-of-run "Output Directory" print line (line 1280) to show the full subdirectory path
- [x] 2.4 Verify: run the diagnostic in real-hardware mode (or simulation with a mock) and confirm the printed path and file listing reference the subdirectory

## 3. Update `main()` to re-interpret `--output-dir` as parent directory

- [x] 3.1 At line 1166-1169, ensure `output_dir` resolves to the parent directory (default `Path("smc3_diagnostic_output")`) and pass it to `DiagnosticSession` — no behavioral change needed since the current code already passes the parent path
- [x] 3.2 Update the print statement at line 1194 to show the parent directory while noting that files go into a timestamped subdirectory
- [x] 3.3 Verify: run with `--output-dir /tmp/custom` and confirm the subdirectory is created at `/tmp/custom/YYYY-MM-DD_HH-MM-SS/`

## 4. Update tests to account for subdirectory structure

- [x] 4.1 Update `test_output_directory_non_overwrite` (line 375) to assert that files are inside the timestamped subdirectory, not the parent
- [x] 4.2 Update the CLI integration test (line 809) to find files within the subdirectory using `output_dir.glob("*")` then `subdir.glob("*.csv")` etc.
- [x] 4.3 Update the single-motor test (line 977) to account for the subdirectory layer
- [x] 4.4 Update the exception test (line 1043) to find summary files in the subdirectory
- [x] 4.5 Update the factory test (line 1125) to account for the subdirectory layer
- [x] 4.6 Update any other tests that assert `output_dir.glob("*.csv")` or `output_dir.glob("*.log")` or `output_dir.glob("*.txt")` to first resolve the subdirectory
- [x] 4.7 Verify: run the full test suite with `pytest src/calibration/test_readback_diagnostic.py -v` and confirm all tests pass

## 5. Verify `.gitignore` coverage and final validation

- [x] 5.1 Confirm `.gitignore` line 2 (`smc3_diagnostic_output/`) covers all subdirectories — no change needed
- [x] 5.2 Run `openspec validate --change run-timestamped-output-directories` to confirm the change artifacts are valid
- [x] 5.3 Verify Python syntax: run `python -m py_compile src/calibration/smc3_readback_diagnostic.py` and confirm no syntax errors
