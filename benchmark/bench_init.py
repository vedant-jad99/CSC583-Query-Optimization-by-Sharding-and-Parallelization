"""
bench_init.py
─────────────
Benchmarks C++ engine initialization time — mmap, VByte decode,
and in-memory index construction.

Invocation (via Makefile using venv Python, not directly):
    $(PYTHON) benchmark/scripts/bench_init.py \\
        --engine ./run_engine \\
        --index  index.bin \\
        --runs   20 \\
        --phase  1 \\
        --output-dir benchmark/results

The engine binary must support the --bench-init flag, which:
    - Loads the index
    - Prints: INIT_TIME_MS: <float>
    - Exits

Design:
    - Runs the engine as a subprocess N times
    - Records init time from stdout per run
    - Reports: mean, median, p95, p99, min, max
    - Writes JSON result to output-dir/phase{N}/init_TIMESTAMP.json

Author: Vedant Keshav Jadhav
Phase:  1, 2, 3 (portable)
"""

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime
from statistics import mean, median

import numpy as np


# ── Argument parsing ──────────────────────────────────────────────────── #

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Benchmark engine initialization time")
    p.add_argument("--engine",     required=True, help="Path to engine binary (e.g. ./run_engine)")
    p.add_argument("--index",      required=True, help="Path to index.bin (or shard directory)")
    p.add_argument("--runs",       type=int, default=20, help="Number of measurement runs (default: 20)")
    p.add_argument("--phase",      type=int, required=True, help="Phase number (1, 2, or 3)")
    p.add_argument("--output-dir", default="benchmark/results", help="Root results directory")
    return p.parse_args()


# ── Core measurement ──────────────────────────────────────────────────── #

def measure_init(engine: str, index: str) -> float:
    """
    Run the engine with --bench-init and parse INIT_TIME_MS from stdout.

    Returns:
        Init time in milliseconds.

    Raises:
        RuntimeError: If the engine exits non-zero or output is malformed.
    """
    result = subprocess.run(
        [engine, index, "--bench-init"],
        capture_output=True,
        text=True,
        timeout=60
    )

    if result.returncode != 0:
        raise RuntimeError(
            f"Engine exited with code {result.returncode}.\n"
            f"stderr: {result.stderr.strip()}"
        )

    for line in result.stdout.splitlines():
        if line.startswith("INIT_TIME_MS:"):
            return float(line.split(":")[1].strip())

    raise RuntimeError(
        f"INIT_TIME_MS not found in engine output.\n"
        f"stdout: {result.stdout.strip()}"
    )


def compute_stats(times: list[float]) -> dict:
    return {
        "mean":   round(mean(times), 4),
        "median": round(median(times), 4),
        "p95":    round(float(np.percentile(times, 95)), 4),
        "p99":    round(float(np.percentile(times, 99)), 4),
        "min":    round(min(times), 4),
        "max":    round(max(times), 4),
    }


# ── Output ────────────────────────────────────────────────────────────── #

def write_result(args: argparse.Namespace, times: list[float]) -> str:
    stats = compute_stats(times)

    result = {
        "phase":      args.phase,
        "timestamp":  datetime.now().isoformat(),
        "engine":     args.engine,
        "index":      args.index,
        "runs":       args.runs,
        "init_time_ms": stats,
        "raw_times_ms": [round(t, 4) for t in times],
    }

    out_dir = os.path.join(args.output_dir, f"phase{args.phase}")
    os.makedirs(out_dir, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path  = os.path.join(out_dir, f"init_{timestamp}.json")

    with open(out_path, "w") as f:
        json.dump(result, f, indent=2)

    return out_path


def print_summary(times: list[float]) -> None:
    stats = compute_stats(times)
    print("\n── Init Time Results ───────────────────────────────────────")
    print(f"  Runs:    {len(times)}")
    print(f"  Mean:    {stats['mean']:.4f} ms")
    print(f"  Median:  {stats['median']:.4f} ms")
    print(f"  p95:     {stats['p95']:.4f} ms")
    print(f"  p99:     {stats['p99']:.4f} ms")
    print(f"  Min:     {stats['min']:.4f} ms")
    print(f"  Max:     {stats['max']:.4f} ms")
    print()


# ── Entry point ───────────────────────────────────────────────────────── #

def main() -> None:
    args = parse_args()

    if not os.path.isfile(args.engine):
        print(f"Error: engine binary not found: {args.engine}", file=sys.stderr)
        sys.exit(1)

    if not os.path.exists(args.index):
        print(f"Error: index not found: {args.index}", file=sys.stderr)
        sys.exit(1)

    print(f"Benchmarking init time: {args.engine} {args.index}")
    print(f"Runs: {args.runs}")

    times: list[float] = []
    for i in range(args.runs):
        t = measure_init(args.engine, args.index)
        times.append(t)
        print(f"  Run {i+1:3d}/{args.runs}: {t:.4f} ms")

    print_summary(times)
    out_path = write_result(args, times)
    print(f"Results written to: {out_path}")


if __name__ == "__main__":
    main()
