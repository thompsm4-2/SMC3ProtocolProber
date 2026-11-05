# H3 v0.3.5.1 CommandHub diagnostic

This revision fixes the `_clamp_position` runtime error in v0.3.5 and adds non-hardware smoke tests around the complete manual CLI command path.

The tests use `tests/serial.py`, a tiny pyserial-compatible echo/write recorder. They do not connect to or move the H3.

On the real Linux system, `pyserial` must be installed and `/dev/ttyACM0` is passed to the manual example.

### Calibration sweep options

`examples/h3_calibrate.py` accepts `--settle 0` (no deliberate settling delay) and
`--no-observe` (run the sweep continuously without observation prompts). For example:

```text
python examples/h3_calibrate.py /dev/ttyACM0 --start 0 --end 20 --step 1 --settle 0 --no-observe
```

With `--no-observe`, each commanded position is printed and the sweep proceeds directly
to the next position. The normal cleanup still returns all three motors to center.
