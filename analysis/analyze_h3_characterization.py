#!/usr/bin/env python3
"""Analyze DOF Reality H3 characterization TX and WT901C sensor CSV logs.

Uses only the Python standard library. Does not modify input files.
"""
from __future__ import annotations
import argparse
import csv
import json
import math
import statistics
from collections import Counter, defaultdict
from pathlib import Path

ANGLE_FIELDS = ("roll_deg", "pitch_deg", "yaw_deg")
SENSOR_FIELDS = ANGLE_FIELDS + (
    "accel_x_g", "accel_y_g", "accel_z_g",
    "gyro_x_dps", "gyro_y_dps", "gyro_z_dps",
    "mag_x", "mag_y", "mag_z",
)

def read_csv(path: Path):
    with path.open("r", newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        return reader.fieldnames or [], list(reader)

def number(value):
    try:
        if value is None or value == "":
            return None
        x = float(value)
        return x if math.isfinite(x) else None
    except (TypeError, ValueError):
        return None

def mean(values):
    return statistics.mean(values) if values else None

def stdev(values):
    return statistics.stdev(values) if len(values) > 1 else (0.0 if values else None)

def regression(xs, ys):
    pairs = [(x, y) for x, y in zip(xs, ys) if x is not None and y is not None]
    if len(pairs) < 2:
        return {"slope": None, "intercept": None, "r2": None, "n": len(pairs)}
    xvals = [p[0] for p in pairs]
    yvals = [p[1] for p in pairs]
    xm, ym = mean(xvals), mean(yvals)
    ssx = sum((x-xm)**2 for x in xvals)
    ssy = sum((y-ym)**2 for y in yvals)
    if ssx == 0:
        return {"slope": None, "intercept": None, "r2": None, "n": len(pairs)}
    slope = sum((x-xm)*(y-ym) for x, y in pairs) / ssx
    intercept = ym - slope*xm
    ss_res = sum((y-(slope*x+intercept))**2 for x, y in pairs)
    r2 = (1 - ss_res/ssy) if ssy else 1.0
    return {"slope": slope, "intercept": intercept, "r2": r2, "n": len(pairs)}

def summarize(tx_rows, sensor_rows):
    tx_types = Counter((r.get("command_type") or "").strip() for r in tx_rows)
    tx_status = Counter((r.get("status") or "").strip() for r in tx_rows)
    tx_motors = Counter((r.get("motor") or "").strip() for r in tx_rows if (r.get("motor") or "").strip())
    position_rows = [r for r in tx_rows if r.get("command_type") == "POSITION"]
    position_by_motor = defaultdict(list)
    for r in position_rows:
        p = number(r.get("position"))
        if p is not None:
            position_by_motor[(r.get("motor") or "").strip()].append(int(p))

    sensor_groups = defaultdict(list)
    sensor_elapsed = []
    sample_indices = []
    for r in sensor_rows:
        key = (
            r.get("phase", ""),
            r.get("sweep_direction", ""),
            r.get("offset", ""),
            r.get("A", ""), r.get("B", ""), r.get("C", ""),
        )
        sensor_groups[key].append(r)
        t = number(r.get("elapsed_s"))
        if t is not None:
            sensor_elapsed.append(t)
        si = number(r.get("sample_index"))
        if si is not None:
            sample_indices.append(int(si))

    group_summaries = []
    for key, rows in sorted(sensor_groups.items(), key=lambda kv: (
        min((number(r.get("elapsed_s")) or 0) for r in kv[1]), kv[0]
    )):
        item = {
            "phase": key[0], "sweep_direction": key[1], "offset": key[2],
            "A": key[3], "B": key[4], "C": key[5], "n": len(rows),
        }
        times = [number(r.get("elapsed_s")) for r in rows]
        times = [x for x in times if x is not None]
        item["start_elapsed_s"] = min(times) if times else None
        item["end_elapsed_s"] = max(times) if times else None
        for field in SENSOR_FIELDS:
            vals = [number(r.get(field)) for r in rows]
            vals = [x for x in vals if x is not None]
            item[field + "_mean"] = mean(vals)
            item[field + "_sd"] = stdev(vals)
            item[field + "_min"] = min(vals) if vals else None
            item[field + "_max"] = max(vals) if vals else None
        group_summaries.append(item)

    elapsed_deltas = [b-a for a, b in zip(sensor_elapsed, sensor_elapsed[1:])]
    positive_deltas = [d for d in elapsed_deltas if d >= 0]
    gyro_values = {
        field: [number(r.get(field)) for r in sensor_rows]
        for field in ("gyro_x_dps", "gyro_y_dps", "gyro_z_dps")
    }
    gyro_values = {k: [v for v in vals if v is not None] for k, vals in gyro_values.items()}

    # Regression uses distinct group means for each sweep direction, not every
    # individual sensor row, so positions with an extra sample are not overweighted.
    regressions = {}
    for direction in sorted({g["sweep_direction"] for g in group_summaries if g["phase"] == "sweep"}):
        groups = [g for g in group_summaries if g["phase"] == "sweep" and g["sweep_direction"] == direction]
        xs = [number(g["offset"]) for g in groups]
        regressions[direction] = {}
        for axis in ANGLE_FIELDS:
            ys = [g[axis + "_mean"] for g in groups]
            regressions[direction][axis] = regression(xs, ys)

    summary = {
        "tx": {
            "rows": len(tx_rows),
            "command_types": dict(tx_types),
            "statuses": dict(tx_status),
            "motor_rows": dict(tx_motors),
            "position_commands_by_motor": {m: {"count": len(v), "min": min(v), "max": max(v), "sequence": v}
                                           for m, v in position_by_motor.items()},
            "all_full_writes": all(
                number(r.get("bytes_written")) == number(r.get("expected"))
                for r in tx_rows if number(r.get("bytes_written")) is not None and number(r.get("expected")) is not None
            ),
        },
        "sensor": {
            "rows": len(sensor_rows),
            "phase_counts": dict(Counter(r.get("phase", "") for r in sensor_rows)),
            "motor_counts": dict(Counter(r.get("motor", "") for r in sensor_rows)),
            "sample_index_min": min(sample_indices) if sample_indices else None,
            "sample_index_max": max(sample_indices) if sample_indices else None,
            "elapsed_start_s": min(sensor_elapsed) if sensor_elapsed else None,
            "elapsed_end_s": max(sensor_elapsed) if sensor_elapsed else None,
            "elapsed_span_s": (max(sensor_elapsed)-min(sensor_elapsed)) if sensor_elapsed else None,
            "sample_interval_median_s": statistics.median(positive_deltas) if positive_deltas else None,
            "sample_gaps_over_0_2s": sum(d > 0.2 for d in positive_deltas),
            "gyro_all_zero": {k: bool(vals) and all(v == 0 for v in vals) for k, vals in gyro_values.items()},
        },
        "regression_by_sweep_direction": regressions,
        "groups": group_summaries,
    }
    return summary

def write_outputs(summary, outdir: Path):
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / "analysis_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    groups = summary["groups"]
    if groups:
        with (outdir / "sensor_group_summary.csv").open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(groups[0].keys()))
            writer.writeheader()
            writer.writerows(groups)
    tx, sensor = summary["tx"], summary["sensor"]
    lines = [
        "# Characterization Analysis",
        "",
        "Generated by `analyze_h3_characterization.py` using Python standard library.",
        "",
        "## TX log",
        f"- Rows: {tx['rows']}",
        f"- Command types: `{tx['command_types']}`",
        f"- Status counts: `{tx['statuses']}`",
        f"- All comparable writes have matching byte counts: **{tx['all_full_writes']}**",
        f"- Position commands by motor: `{tx['position_commands_by_motor']}`",
        "",
        "## Sensor log",
        f"- Rows: {sensor['rows']}",
        f"- Phase counts: `{sensor['phase_counts']}`",
        f"- Motor counts: `{sensor['motor_counts']}`",
        f"- Sample index range: {sensor['sample_index_min']}–{sensor['sample_index_max']}",
        f"- Elapsed span: {sensor['elapsed_span_s']:.6f} s" if sensor["elapsed_span_s"] is not None else "- Elapsed span: unavailable",
        f"- Median sample interval: {sensor['sample_interval_median_s']:.6f} s" if sensor["sample_interval_median_s"] is not None else "- Median sample interval: unavailable",
        f"- Gaps over 0.2 s: {sensor['sample_gaps_over_0_2s']}",
        f"- Gyro channels all zero: `{sensor['gyro_all_zero']}`",
        "",
        "## Direction-specific exploratory regressions",
        "",
        "Regressions use distinct phase/offset group means, not individual rows. They are descriptive only; do not treat them as calibrated response constants.",
        "",
    ]
    for direction, axes in summary["regression_by_sweep_direction"].items():
        lines += [f"### {direction}", ""]
        for axis, result in axes.items():
            lines.append(f"- {axis}: slope={result['slope']}, intercept={result['intercept']}, R²={result['r2']}, groups={result['n']}")
        lines.append("")
    lines += [
        "## Interpretation cautions",
        "",
        "- A logged full serial write is not proof of controller execution.",
        "- TX `READ` rows represent transmitted read requests; this TX file does not record response bytes.",
        "- The sensor CSV contains WT901C measurements.",
        "- Exact-zero gyro channels require sensor/parser/configuration investigation.",
        "- Yaw is direction/time dependent in this run and is not a validated Motor C calibration.",
        "- Settling time cannot be inferred from a single group mean; use timestamped transient data and validated gyro/angle streams.",
        "",
    ]
    (outdir / "analysis_report.md").write_text("\n".join(lines), encoding="utf-8")

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--tx", required=True, type=Path)
    ap.add_argument("--sensor", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    args = ap.parse_args()
    tx_fields, tx_rows = read_csv(args.tx)
    sensor_fields, sensor_rows = read_csv(args.sensor)
    if not tx_rows or not sensor_rows:
        raise SystemExit("Both CSV files must contain data rows.")
    required_tx = {"command_type", "status", "bytes_written", "expected"}
    required_sensor = {"phase", "sweep_direction", "offset", "elapsed_s", "roll_deg", "pitch_deg", "yaw_deg"}
    if not required_tx.issubset(set(tx_fields)):
        raise SystemExit(f"TX CSV missing required columns: {sorted(required_tx-set(tx_fields))}")
    if not required_sensor.issubset(set(sensor_fields)):
        raise SystemExit(f"Sensor CSV missing required columns: {sorted(required_sensor-set(sensor_fields))}")
    summary = summarize(tx_rows, sensor_rows)
    write_outputs(summary, args.out)
    print(f"Analyzed {len(tx_rows)} TX rows and {len(sensor_rows)} sensor rows.")
    print(f"Wrote outputs to {args.out}")

if __name__ == "__main__":
    main()
