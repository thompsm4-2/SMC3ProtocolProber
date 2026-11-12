# Spec Delta

## ADDED Requirements

### Requirement: Each run creates a timestamped subdirectory

When running in real-hardware mode (not `--simulate`), the system SHALL create a subdirectory inside the output directory named with a filesystem-safe timestamp in `YYYY-MM-DD_HH-MM-SS` format (e.g., `2026-11-11_14-30-00`). The timestamp is generated once at the start of the run and applies to all files produced by that run.

#### Scenario: Timestamped subdirectory is created for a run

- **GIVEN** the diagnostic utility is run in real-hardware mode with default output directory
- **THEN** a subdirectory named `YYYY-MM-DD_HH-MM-SS` is created inside `smc3_diagnostic_output/`
- **THEN** all diagnostic output files for that run are placed inside that subdirectory

#### Scenario: Timestamp is generated once at run start

- **GIVEN** a diagnostic run that lasts more than one second
- **THEN** all files produced by that run share the same timestamp derived from the run-start time

#### Scenario: Custom parent directory with timestamped subdirectory

- **GIVEN** the user specifies `--output-dir /custom/path`
- **THEN** a timestamped subdirectory is created inside `/custom/path`
- **THEN** all diagnostic output files are placed inside that subdirectory

#### Scenario: Simulate mode creates no directories

- **GIVEN** the `--simulate` flag is passed
- **THEN** no output directories or subdirectories are created
- **THEN** no diagnostic output files are written to disk

### Requirement: File naming conventions are preserved

All diagnostic output files SHALL retain their existing naming patterns, including the embedded timestamp format `%Y%m%d_%H%M%S` (e.g., `requests_20261111_143000.csv`, `raw_serial_20261111_143000.log`). The file-level timestamp and the subdirectory timestamp are both derived from the same run-start time.

#### Scenario: Requests CSV preserves naming pattern

- **GIVEN** a run starting at 2026-11-11 14:30:00
- **THEN** the requests file is named `requests_20261111_143000.csv` inside the `2026-11-11_14-30-00` subdirectory

#### Scenario: Raw serial log preserves naming pattern

- **GIVEN** a run starting at 2026-11-11 14:30:00
- **THEN** the raw serial log is named `raw_serial_20261111_143000.log` inside the `2026-11-11_14-30-00` subdirectory

#### Scenario: Decoded readbacks CSV preserves naming pattern

- **GIVEN** a run starting at 2026-11-11 14:30:00
- **THEN** the decoded readbacks file is named `decoded_readbacks_20261111_143000.csv` inside the `2026-11-11_14-30-00` subdirectory

#### Scenario: Active test CSV preserves naming pattern

- **GIVEN** a run starting at 2026-11-11 14:30:00
- **THEN** the active test file is named `active_test_20261111_143000.csv` inside the `2026-11-11_14-30-00` subdirectory

#### Scenario: Summary text preserves naming pattern

- **GIVEN** a run starting at 2026-11-11 14:30:00
- **THEN** the summary file is named `summary_20261111_143000.txt` inside the `2026-11-11_14-30-00` subdirectory

### Requirement: Multiple runs produce separate subdirectories

When multiple diagnostic runs are executed, each run SHALL produce its own timestamped subdirectory. Runs that start at different times produce subdirectories with different timestamps. Runs that start at the same wall-clock time produce subdirectories with the same timestamp and append to existing files (preserving the current non-overwrite behavior).

#### Scenario: Two runs at different times produce separate subdirectories

- **GIVEN** a first diagnostic run starting at 2026-11-11 10:00:00
- **AND** a second diagnostic run starting at 2026-11-11 14:30:00
- **THEN** the output directory contains two subdirectories: `2026-11-11_10-00-00` and `2026-11-11_14-30-00`
- **THEN** each subdirectory contains only the files from its respective run

#### Scenario: Two runs at the same time append to existing files

- **GIVEN** two diagnostic runs starting at the same frozen timestamp
- **THEN** both runs write to the same subdirectory
- **THEN** files are appended, not overwritten (preserving existing non-overwrite behavior)

### Requirement: CLI output reflects new directory structure

The diagnostic utility SHALL print the full path of the timestamped subdirectory at the end of a successful run, and list files within that subdirectory.

#### Scenario: Output shows timestamped subdirectory path

- **GIVEN** a successful diagnostic run
- **THEN** the utility prints the full path of the run's subdirectory
- **THEN** the utility lists the files generated within that subdirectory
