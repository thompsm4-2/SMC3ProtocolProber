# Proposal

## Why

Diagnostic runs currently all write into a single flat directory (`smc3_diagnostic_output/`), with files differentiated only by embedded timestamps in their names. This makes it difficult to locate all files belonging to a specific run, especially when multiple runs occur in the same day or when comparing runs side by side. Grouping all files for a run into its own subdirectory improves organization, simplifies archival, and makes it easier to identify and clean up old runs.

## What Changes

- The `smc3_diagnostic_output` directory remains the parent output directory.
- At the start of each diagnostic run, a subdirectory is created inside `smc3_diagnostic_output` named with a filesystem-safe timestamp in `YYYY-MM-DD_HH-MM-SS` format (e.g., `2026-11-11_14-30-00`).
- The timestamp for the subdirectory is generated once at run start and reused for both the subdirectory name and the file-level timestamps within that run.
- All diagnostic output files (CSV logs, raw serial log, decoded readbacks, active test CSV, summary text) are written into the run's subdirectory instead of directly into the parent.
- File naming conventions and embedded timestamps are preserved exactly as they are today (e.g., `requests_20261111_143000.csv`, `raw_serial_20261111_143000.log`).
- The `--output-dir` CLI flag is repurposed: when provided, it sets the parent directory (default `smc3_diagnostic_output`); the timestamped subdirectory is always created automatically inside it.
- Simulation mode (`--simulate`) creates no directories or files (existing behavior unchanged).

## Capabilities

### Modified Capabilities

- **diagnostic-simulation**: The existing spec states that simulate mode skips creating output files and directories. This change modifies the real-hardware output path behavior (parent directory + timestamped subdirectory) while preserving the simulate-mode no-op behavior.

## Impact

- `src/calibration/smc3_readback_diagnostic.py` — `DiagnosticSession.__init__` / `_setup_output_files`, main() output-dir handling, `_SimulateSession` path, and the `iterdir()` listing at the end.
- `src/calibration/test_readback_diagnostic.py` — Tests that assert file paths, directory structure, and the non-overwrite behavior will need updates to account for the new subdirectory layer.
- `.gitignore` — No change needed; `smc3_diagnostic_output/` still covers all subdirectories.
