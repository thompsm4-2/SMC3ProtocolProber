"""v0.4.1-compatible CSV logging for the v0.5 sweep driver.

Responsibility (Implementation.md section 11, task T1.2/T6.x):
v0.4.1-compatible TX CSV and compatible sensor CSV handling.

This module is a Phase 1 skeleton placeholder. Its behavior is
implemented by the Phase 6 logging tasks and is not yet written.

Planned responsibilities:

- TX CSV: preserve the original ten columns in their existing order
  (timestamp, elapsed_ms, command_type, motor, position, bytes_hex,
  bytes_written, expected, status, error) with unchanged meanings and
  the existing OK/SHORT/ERROR status vocabulary. Append the v0.5
  fields after the original ten: run_id, point_index, attempt_seq,
  post_close. bytes_written comes from the serial-proxy return value;
  expected comes from the frame length. Center/control rows use a
  documented point_index = -1 sentinel classification.
- Sensor CSV: preserve the v0.4.1 schema exactly, including the
  existing CSV_FIELDS order and names (to be confirmed by inspecting
  the actual historical v0.4.1 source before implementing writers,
  task T6.1). Never populate sensor fields with fabricated or
  placeholder measurements; if sensor collection was not part of a
  run, report that it was not collected.
- The existing analyzer analysis/analyze_h3_characterization.py must
  keep reading both historical v0.4.1 CSVs and v0.5-compatible CSVs
  via csv.DictReader/.get() (verified by the T6.5 compatibility test).
"""
