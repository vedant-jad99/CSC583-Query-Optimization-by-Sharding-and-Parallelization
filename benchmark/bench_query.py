"""
bench_query.py
──────────────
Benchmarks query latency and throughput against the C++ engine.

Invocation (via Makefile using venv Python, not directly):
    $(PYTHON) benchmark/scripts/bench_query.py \\
        --engine    ./run_engine \\
        --index     index.bin \\
        --queries   benchmark/queries/ \\
        --warmup    10 \\
        --runs      50 \\
        --phase     1 \\
        --output-dir benchmark/results

Protocol:
    1. Engine launched in --bench mode (persistent stdin/stdout loop)
    2. Engine prints READY when fully initialized
    3. Script sends warmup queries (results discarded)
    4. Script sends each query --runs times, recording round-trip time
    5. Engine exits on EOF or EXIT command
    6. Stats computed per query category (short/medium/complex)
    7. Combined JSON + per-category JSONs written to output-dir

Metrics:
    - Latency: mean, median, p95, p99, min, max (per category + combined)
    - Throughput: queries per second (total batch time)

Output:
    - benchmark/results/phase{N}/query_short_TIMESTAMP.json
    - benchmark/results/phase{N}/query_medium_TIMESTAMP.json
    - benchmark/results/phase{N}/query_complex_TIMESTAMP.json
    - benchmark/results/phase{N}/query_combined_TIMESTAMP.json

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
from typing import Iterator

import numpy as np


# ── Query file loading ────────────────────────────────────────────────── #

QUERY_FILES = {
    "short":   "short.txt",
    "medium":  "medium.txt",
    "complex": "complex.txt",
}


def load_queries(queries_dir: str, category: str) -> list[str]:
    """
    Load queries from a file, skipping blank lines and comments (#).

    Args:
        queries_dir: Directory containing query files.
        category:    One of short / medium / complex.

    Returns:
        List of query strings.
    """
    filepath = os.path.join(queries_dir, QUERY_FILES[category])
    if not os.path.isfile(filepath):
        raise FileNotFoundError(f"Query file not found: {filepath}")

    queries: list[str] = []
    with open(filepath, "r") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                queries.append(line)

    if not queries:
        raise ValueError(f"No queries found in {filepath}")

    return queries


# ── Engine process management ─────────────────────────────────────────── #

class EngineProcess:
    """
    Manages a persistent engine subprocess in --bench mode.

    The engine:
      - Prints READY\n when initialized
      - Reads one query per line from stdin
      - Prints space-separated doc IDs (or empty line) for each query
      - Exits on EXIT command or EOF
    """

    def __init__(self, engine: str, index: str) -> None:
        self._proc = subprocess.Popen(
            [engine, index, "--bench"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,  # line buffered
        )
        self._wait_for_ready()

    def _wait_for_ready(self, timeout: float = 60.0) -> None:
        """Block until engine prints READY."""
        start = time.perf_counter()
        while True:
            line = self._proc.stdout.readline()
            if line.strip() == "READY":
                return
            if time.perf_counter() - start > timeout:
                raise TimeoutError("Engine did not print READY within timeout")
            if self._proc.poll() is not None:
                raise RuntimeError(
                    f"Engine exited before printing READY.\n"
                    f"stderr: {self._proc.stderr.read()}"
                )

    def query(self, q: str) -> tuple[float, str]:
        """
        Send one query, measure round-trip time.

        Returns:
            (latency_ms, result_line)
        """
        self._proc.stdin.write(q + "\n")
        self._proc.stdin.flush()

        t0 = time.perf_counter()
        result = self._proc.stdout.readline()
        t1 = time.perf_counter()

        latency_ms = (t1 - t0) * 1000.0
        return latency_ms, result.strip()

    def shutdown(self) -> None:
        try:
            self._proc.stdin.write("EXIT\n")
            self._proc.stdin.flush()
        except BrokenPipeError:
            pass
        try:
            self._proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self._proc.kill()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.shutdown()


# ── Measurement ───────────────────────────────────────────────────────── #

def warmup(engine: EngineProcess, queries: list[str], n: int) -> None:
    """Send n warmup queries, discarding results."""
    warmup_queries = (queries * ((n // len(queries)) + 1))[:n]
    for q in warmup_queries:
        engine.query(q)


def measure_category(
    engine: EngineProcess,
    queries: list[str],
    runs: int,
) -> dict:
    """
    Measure latency for all queries in a category.

    Each query is sent `runs` times. Records per-query and aggregate stats.

    Returns:
        dict with latencies, throughput, per-query breakdown.
    """
    all_latencies: list[float] = []
    per_query: list[dict] = []

    batch_start = time.perf_counter()

    for q in queries:
        q_latencies: list[float] = []
        for _ in range(runs):
            latency_ms, _ = engine.query(q)
            q_latencies.append(latency_ms)
        all_latencies.extend(q_latencies)
        per_query.append({
            "query":      q,
            "mean_ms":    round(mean(q_latencies), 4),
            "median_ms":  round(median(q_latencies), 4),
            "p99_ms":     round(float(np.percentile(q_latencies, 99)), 4),
            "min_ms":     round(min(q_latencies), 4),
            "max_ms":     round(max(q_latencies), 4),
        })

    batch_end = time.perf_counter()
    total_queries = len(queries) * runs
    total_time_s  = batch_end - batch_start
    throughput_qps = total_queries / total_time_s

    return {
        "query_count":    len(queries),
        "runs_per_query": runs,
        "total_queries":  total_queries,
        "latency_ms": {
            "mean":   round(mean(all_latencies), 4),
            "median": round(median(all_latencies), 4),
            "p95":    round(float(np.percentile(all_latencies, 95)), 4),
            "p99":    round(float(np.percentile(all_latencies, 99)), 4),
            "min":    round(min(all_latencies), 4),
            "max":    round(max(all_latencies), 4),
        },
        "throughput_qps": round(throughput_qps, 2),
        "per_query":      per_query,
    }


# ── Stats helpers ─────────────────────────────────────────────────────── #

def compute_stats(values: argparse.Namespace) -> argparse.Namespace:
    pass  # inline in measure_category


# ── Output ────────────────────────────────────────────────────────────── #

def build_result_doc(
    args: argparse.Namespace,
    category: str,
    data: dict,
) -> dict:
    return {
        "phase":     args.phase,
        "timestamp": datetime.now().isoformat(),
        "engine":    args.engine,
        "index":     args.index,
        "category":  category,
        "warmup_queries": args.warmup,
        "runs_per_query": args.runs,
        **data,
    }


def write_json(out_dir: str, name: str, doc: dict) -> str:
    os.makedirs(out_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = os.path.join(out_dir, f"query_{name}_{timestamp}.json")
    with open(path, "w") as f:
        json.dump(doc, f, indent=2)
    return path


def print_category_summary(category: str, data: dict) -> None:
    lat = data["latency_ms"]
    print(f"\n  [{category.upper()}]  {data['query_count']} queries × {data['runs_per_query']} runs")
    print(f"    Latency  mean={lat['mean']:.4f}ms  median={lat['median']:.4f}ms  "
          f"p95={lat['p95']:.4f}ms  p99={lat['p99']:.4f}ms  "
          f"min={lat['min']:.4f}ms  max={lat['max']:.4f}ms")
    print(f"    Throughput: {data['throughput_qps']:.2f} QPS")


# ── Argument parsing ──────────────────────────────────────────────────── #

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Benchmark query latency and throughput")
    p.add_argument("--engine",      required=True, help="Path to engine binary")
    p.add_argument("--index",       required=True, help="Path to index.bin")
    p.add_argument("--queries",     required=True, help="Path to queries directory")
    p.add_argument("--warmup",      type=int, default=10,  help="Warmup queries (default: 10)")
    p.add_argument("--runs",        type=int, default=50,  help="Runs per query (default: 50)")
    p.add_argument("--phase",       type=int, required=True, help="Phase number")
    p.add_argument("--output-dir",  default="benchmark/results", help="Root results directory")
    return p.parse_args()


# ── Entry point ───────────────────────────────────────────────────────── #

def main() -> None:
    args = parse_args()

    # Validate inputs
    for attr, label in [("engine", "Engine binary"), ("index", "Index")]:
        path = getattr(args, attr)
        if not os.path.exists(path):
            print(f"Error: {label} not found: {path}", file=sys.stderr)
            sys.exit(1)

    out_dir = os.path.join(args.output_dir, f"phase{args.phase}")
    results: dict[str, dict] = {}

    print(f"\nBenchmarking queries: {args.engine} {args.index}")
    print(f"Warmup: {args.warmup} queries | Runs per query: {args.runs}")

    with EngineProcess(args.engine, args.index) as engine:

        # Load all query categories
        all_queries: dict[str, list[str]] = {}
        for cat in QUERY_FILES:
            try:
                all_queries[cat] = load_queries(args.queries, cat)
                print(f"  Loaded {len(all_queries[cat])} {cat} queries")
            except FileNotFoundError as e:
                print(f"  Warning: {e} — skipping {cat}")

        if not all_queries:
            print("Error: no query files found", file=sys.stderr)
            sys.exit(1)

        # Warmup — use all available queries
        all_flat = [q for qs in all_queries.values() for q in qs]
        print(f"\nRunning {args.warmup} warmup queries...")
        warmup(engine, all_flat, args.warmup)
        print("Warmup complete.\n")

        # Measure each category
        print("── Query Benchmarks ────────────────────────────────────────")
        for cat, queries in all_queries.items():
            print(f"\n  Measuring [{cat}]...")
            data = measure_category(engine, queries, args.runs)
            results[cat] = data
            print_category_summary(cat, data)

            # Write per-category JSON
            doc = build_result_doc(args, cat, data)
            path = write_json(out_dir, cat, doc)
            print(f"  → {path}")

    # Combined result
    if len(results) > 1:
        all_latencies = []
        total_queries  = 0
        for data in results.values():
            total_queries += data["total_queries"]
            all_latencies.extend(
                [q["mean_ms"] for q in data["per_query"]]
            )

        combined = {
            "categories": list(results.keys()),
            "total_queries": total_queries,
            "latency_ms": {
                "mean":   round(mean(all_latencies), 4),
                "median": round(median(all_latencies), 4),
                "p95":    round(float(np.percentile(all_latencies, 95)), 4),
                "p99":    round(float(np.percentile(all_latencies, 99)), 4),
                "min":    round(min(all_latencies), 4),
                "max":    round(max(all_latencies), 4),
            },
            "per_category": results,
        }
        doc = build_result_doc(args, "combined", combined)
        path = write_json(out_dir, "combined", doc)
        print(f"\n  Combined → {path}")

    print("\nDone.\n")


if __name__ == "__main__":
    main()
