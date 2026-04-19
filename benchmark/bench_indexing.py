"""
bench_indexing.py
─────────────────
Benchmarks the Python indexing pipeline — corpus ingestion, normalization,
index construction, VByte encoding, and bin file write.

This is the only benchmark script that runs a Python process (the pipeline
itself), not the C++ engine. It measures wall-clock time and peak memory
for the full index build.

Invocation (via Makefile using venv Python, not directly):
    $(PYTHON) benchmark/scripts/bench_indexing.py \\
        --corpus   data/corpus \\
        --pipeline scripts/main.py \\
        --output   index.bin \\
        --runs     5 \\
        --phase    1 \\
        --output-dir benchmark/results

Why only 5 runs (vs 20 for init, 50 for queries)?
    Index construction is slow — seconds to minutes on a real corpus.
    5 runs gives a stable mean and variance without taking hours.
    For Phase 1 WikiText-2, expect ~30–120s per run depending on corpus size.

Metrics:
    - Wall-clock time for full pipeline (s)
    - Index file size on disk (KB and MB)
    - Peak memory of the pipeline process (via /usr/bin/time or resource module)

Output:
    - benchmark/results/phase{N}/indexing_TIMESTAMP.json

Phase 2 significance:
    Phase 2 runs N pipeline workers in parallel (ProcessPoolExecutor).
    This script measures single-pipeline baseline.
    For Phase 2, run the ShardBuilder and measure total wall time for N shards.
    Expected result: Phase 2 build time ≈ Phase 1 / N (ideal parallelism).
    Actual result will be slightly worse due to process spawn overhead.

Author: Vedant Keshav Jadhav
Phase:  1, 2, 3 (portable)
"""

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from statistics import mean, median

import numpy as np


# ── Argument parsing ──────────────────────────────────────────────────── #

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Benchmark index construction time")
    p.add_argument("--corpus",      required=True,  help="Path to corpus directory")
    p.add_argument("--pipeline",    required=True,  help="Path to pipeline entry point (scripts/main.py)")
    p.add_argument("--output",      default="index.bin", help="Output index file path (default: index.bin)")
    p.add_argument("--runs",        type=int, default=5,  help="Number of runs (default: 5)")
    p.add_argument("--phase",       type=int, required=True, help="Phase number")
    p.add_argument("--output-dir",  default="benchmark/results", help="Root results directory")
    p.add_argument("--python",      default=sys.executable,
                   help="Python interpreter to use (default: current interpreter)")
    return p.parse_args()


# ── Single pipeline run ───────────────────────────────────────────────── #

def run_pipeline(python: str, pipeline: str, corpus: str, output: str) -> dict:
    """
    Run the indexing pipeline once and measure wall-clock time and peak memory.

    Uses /usr/bin/time -v (Linux) or \time -l (macOS) for peak RSS.
    Falls back to wall-clock only if time utility unavailable.

    Returns:
        dict with wall_time_s, index_size_kb, peak_rss_kb (or None)
    """
    import platform

    # Build command
    cmd = [python, pipeline, "--corpus", corpus, "--out", output]

    # Attempt to use system time for memory measurement
    os_name = platform.system()
    use_time_util = False

    if os_name == "Linux":
        time_cmd = ["/usr/bin/time", "-v"] + cmd
        use_time_util = True
    elif os_name == "Darwin":
        time_cmd = ["/usr/bin/time", "-l"] + cmd
        use_time_util = True

    t0 = time.perf_counter()

    if use_time_util:
        result = subprocess.run(
            time_cmd,
            capture_output=True,
            text=True,
        )
    else:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
        )

    t1 = time.perf_counter()

    wall_time_s = t1 - t0

    if result.returncode != 0:
        raise RuntimeError(
            f"Pipeline exited with code {result.returncode}.\n"
            f"stdout: {result.stdout.strip()}\n"
            f"stderr: {result.stderr.strip()}"
        )

    # Parse peak RSS
    peak_rss_kb = None
    if use_time_util:
        time_output = result.stderr  # /usr/bin/time writes to stderr
        if os_name == "Linux":
            for line in time_output.splitlines():
                if "Maximum resident set size" in line:
                    try:
                        peak_rss_kb = int(line.strip().split()[-1])
                    except ValueError:
                        pass
        elif os_name == "Darwin":
            for line in time_output.splitlines():
                if "maximum resident set size" in line:
                    try:
                        peak_bytes = int(line.strip().split()[0])
                        peak_rss_kb = peak_bytes // 1024
                    except ValueError:
                        pass

    # Index file size
    if not os.path.isfile(output):
        raise RuntimeError(f"Pipeline did not produce output file: {output}")

    index_size_bytes = os.path.getsize(output)
    index_size_kb    = index_size_bytes / 1024.0

    return {
        "wall_time_s":  round(wall_time_s, 4),
        "index_size_kb": round(index_size_kb, 2),
        "index_size_mb": round(index_size_kb / 1024.0, 4),
        "peak_rss_kb":   peak_rss_kb,
    }


# ── Statistics ────────────────────────────────────────────────────────── #

def compute_stats(values: list[float]) -> dict:
    return {
        "mean":   round(mean(values), 4),
        "median": round(median(values), 4),
        "p95":    round(float(np.percentile(values, 95)), 4),
        "p99":    round(float(np.percentile(values, 99)), 4),
        "min":    round(min(values), 4),
        "max":    round(max(values), 4),
    }


# ── Output ────────────────────────────────────────────────────────────── #

def write_result(args: argparse.Namespace, runs_data: list[dict]) -> str:
    times   = [r["wall_time_s"]   for r in runs_data]
    rss_vals = [r["peak_rss_kb"]  for r in runs_data if r["peak_rss_kb"] is not None]

    # Index size is deterministic — take from last run
    index_size_kb = runs_data[-1]["index_size_kb"]
    index_size_mb = runs_data[-1]["index_size_mb"]

    result = {
        "phase":     args.phase,
        "timestamp": datetime.now().isoformat(),
        "corpus":    args.corpus,
        "pipeline":  args.pipeline,
        "output":    args.output,
        "runs":      args.runs,
        "wall_time_s": compute_stats(times),
        "raw_times_s": [round(t, 4) for t in times],
        "index_size_kb": index_size_kb,
        "index_size_mb": index_size_mb,
        "peak_rss_kb": {
            "mean":   round(mean(rss_vals), 1) if rss_vals else None,
            "max":    round(max(rss_vals), 1)  if rss_vals else None,
        },
    }

    out_dir = os.path.join(args.output_dir, f"phase{args.phase}")
    os.makedirs(out_dir, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path  = os.path.join(out_dir, f"indexing_{timestamp}.json")

    with open(out_path, "w") as f:
        json.dump(result, f, indent=2)

    return out_path


def print_summary(runs_data: list[dict]) -> None:
    times = [r["wall_time_s"] for r in runs_data]
    stats = compute_stats(times)
    index_size_kb = runs_data[-1]["index_size_kb"]

    print("\n── Index Construction Results ──────────────────────────────")
    print(f"  Runs:       {len(times)}")
    print(f"  Mean:       {stats['mean']:.4f} s")
    print(f"  Median:     {stats['median']:.4f} s")
    print(f"  p95:        {stats['p95']:.4f} s")
    print(f"  p99:        {stats['p99']:.4f} s")
    print(f"  Min:        {stats['min']:.4f} s")
    print(f"  Max:        {stats['max']:.4f} s")
    print(f"  Index size: {index_size_kb:.2f} KB  ({index_size_kb/1024:.4f} MB)")

    rss_vals = [r["peak_rss_kb"] for r in runs_data if r["peak_rss_kb"] is not None]
    if rss_vals:
        print(f"  Peak RSS:   {max(rss_vals)} KB  ({max(rss_vals)/1024:.1f} MB)")
    print()


# ── Entry point ───────────────────────────────────────────────────────── #

def main() -> None:
    args = parse_args()

    # Validate
    if not os.path.isdir(args.corpus):
        print(f"Error: corpus directory not found: {args.corpus}", file=sys.stderr)
        sys.exit(1)

    if not os.path.isfile(args.pipeline):
        print(f"Error: pipeline script not found: {args.pipeline}", file=sys.stderr)
        sys.exit(1)

    print(f"Benchmarking index construction")
    print(f"  Corpus:   {args.corpus}")
    print(f"  Pipeline: {args.pipeline}")
    print(f"  Output:   {args.output}")
    print(f"  Runs:     {args.runs}")
    print()

    runs_data: list[dict] = []

    for i in range(args.runs):
        print(f"  Run {i+1}/{args.runs}...", end=" ", flush=True)
        try:
            data = run_pipeline(args.python, args.pipeline, args.corpus, args.output)
            runs_data.append(data)
            rss_str = f"  peak RSS: {data['peak_rss_kb']} KB" if data["peak_rss_kb"] else ""
            print(f"{data['wall_time_s']:.4f} s  |  index: {data['index_size_kb']:.2f} KB{rss_str}")
        except RuntimeError as e:
            print(f"FAILED: {e}", file=sys.stderr)
            sys.exit(1)

    print_summary(runs_data)
    out_path = write_result(args, runs_data)
    print(f"Results written to: {out_path}")


if __name__ == "__main__":
    main()
