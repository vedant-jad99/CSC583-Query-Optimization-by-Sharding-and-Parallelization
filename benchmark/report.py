"""
report.py
─────────
Aggregates benchmark JSON results from one or more phases and produces:
  1. A printed summary table (per phase, per category)
  2. A cross-phase comparison table (when multiple phases provided)
  3. matplotlib plots:
       - Latency distribution (box plot per category)
       - Per-phase throughput (bar chart)
       - Phase comparison (grouped bar chart — mean and p99 latency)
       - Speedup curve (Phase 1 baseline = 1.0)

Invocation (via Makefile using venv Python, not directly):
    $(PYTHON) benchmark/scripts/report.py \\
        --results-dir benchmark/results \\
        --phases 1 2 3 \\
        --output-dir benchmark/results/plots

Author: Vedant Keshav Jadhav
Phase:  1, 2, 3
"""

import argparse
import glob
import json
import os
import sys
from datetime import datetime
from typing import Optional

import matplotlib
matplotlib.use("Agg")  # non-interactive backend — no display required
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import numpy as np


# ── JSON loading ──────────────────────────────────────────────────────── #

def load_phase_results(results_dir: str, phase: int) -> dict:
    """
    Load all JSON result files for a given phase.

    Returns:
        dict with keys: init, memory, short, medium, complex, combined
        Each value is the most recent JSON result for that type, or None.
    """
    phase_dir = os.path.join(results_dir, f"phase{phase}")
    if not os.path.isdir(phase_dir):
        print(f"Warning: no results directory for phase {phase}: {phase_dir}")
        return {}

    results = {}
    type_map = {
        "init":     "init_*.json",
        "short":    "query_short_*.json",
        "medium":   "query_medium_*.json",
        "complex":  "query_complex_*.json",
        "combined": "query_combined_*.json",
    }

    for key, pattern in type_map.items():
        files = sorted(glob.glob(os.path.join(phase_dir, pattern)))
        if files:
            with open(files[-1]) as f:  # most recent
                results[key] = json.load(f)

    # Memory — JSONL file, take last entry
    mem_files = sorted(glob.glob(os.path.join(phase_dir, "memory*.json*")))
    if mem_files:
        with open(mem_files[-1]) as f:
            for line in f:
                line = line.strip()
                if line:
                    results["memory"] = json.loads(line)

    return results


# ── Summary printing ──────────────────────────────────────────────────── #

def print_divider(char: str = "─", width: int = 72) -> None:
    print(char * width)


def print_init_summary(phase: int, data: dict) -> None:
    lat = data.get("init_time_ms", {})
    print(f"\n  Phase {phase} — Init Time")
    print(f"    {'Mean':>10}  {'Median':>10}  {'p95':>10}  {'p99':>10}  {'Min':>10}  {'Max':>10}")
    print(f"    {'ms':>10}  {'ms':>10}  {'ms':>10}  {'ms':>10}  {'ms':>10}  {'ms':>10}")
    print(f"    {lat.get('mean',0):>10.4f}  {lat.get('median',0):>10.4f}  "
          f"{lat.get('p95',0):>10.4f}  {lat.get('p99',0):>10.4f}  "
          f"{lat.get('min',0):>10.4f}  {lat.get('max',0):>10.4f}")


def print_query_summary(phase: int, category: str, data: dict) -> None:
    lat = data.get("latency_ms", {})
    qps = data.get("throughput_qps", 0)
    print(f"\n  Phase {phase} — Query [{category.upper()}]  ({data.get('query_count',0)} queries × {data.get('runs_per_query',0)} runs)")
    print(f"    {'Mean':>10}  {'Median':>10}  {'p95':>10}  {'p99':>10}  {'QPS':>10}")
    print(f"    {'ms':>10}  {'ms':>10}  {'ms':>10}  {'ms':>10}  {'q/s':>10}")
    print(f"    {lat.get('mean',0):>10.4f}  {lat.get('median',0):>10.4f}  "
          f"{lat.get('p95',0):>10.4f}  {lat.get('p99',0):>10.4f}  "
          f"{qps:>10.2f}")


def print_memory_summary(phase: int, data: dict) -> None:
    rss_kb = data.get("peak_rss_kb", 0)
    print(f"\n  Phase {phase} — Peak Memory: {rss_kb} KB ({rss_kb/1024:.1f} MB)")


def print_phase_summary(phase: int, results: dict) -> None:
    print_divider("═")
    print(f"  PHASE {phase} SUMMARY")
    print_divider("═")

    if "init" in results:
        print_init_summary(phase, results["init"])

    for cat in ["short", "medium", "complex"]:
        if cat in results:
            print_query_summary(phase, cat, results[cat])

    if "memory" in results:
        print_memory_summary(phase, results["memory"])


def print_comparison_table(phase_results: dict[int, dict]) -> None:
    phases = sorted(phase_results.keys())
    if len(phases) < 2:
        return

    print_divider("═")
    print("  CROSS-PHASE COMPARISON")
    print_divider("═")

    baseline_phase = phases[0]
    categories = ["short", "medium", "complex"]

    # Header
    header = f"  {'Metric':<35}"
    for ph in phases:
        header += f"  {'Phase '+str(ph):>12}"
    if len(phases) > 1:
        for ph in phases[1:]:
            header += f"  {'vs P'+str(baseline_phase):>10}"
    print(header)
    print_divider()

    # Init time
    row = f"  {'Init time median (ms)':<35}"
    baseval = None
    for ph in phases:
        val = phase_results[ph].get("init", {}).get("init_time_ms", {}).get("median", None)
        if val is not None:
            row += f"  {val:>12.4f}"
            if baseval is None:
                baseval = val
        else:
            row += f"  {'N/A':>12}"
    if baseval and baseval > 0:
        for ph in phases[1:]:
            val = phase_results[ph].get("init", {}).get("init_time_ms", {}).get("median", None)
            if val is not None:
                delta = ((val - baseval) / baseval) * 100
                row += f"  {delta:>+9.1f}%"
    print(row)

    # Per-category metrics
    for cat in categories:
        for metric, label in [("median", "median ms"), ("p99", "p99 ms")]:
            row = f"  {cat.capitalize()+' query '+label:<35}"
            baseval = None
            for ph in phases:
                val = phase_results[ph].get(cat, {}).get("latency_ms", {}).get(metric, None)
                if val is not None:
                    row += f"  {val:>12.4f}"
                    if baseval is None:
                        baseval = val
                else:
                    row += f"  {'N/A':>12}"
            if baseval and baseval > 0:
                for ph in phases[1:]:
                    val = phase_results[ph].get(cat, {}).get("latency_ms", {}).get(metric, None)
                    if val is not None:
                        delta = ((val - baseval) / baseval) * 100
                        row += f"  {delta:>+9.1f}%"
            print(row)

        # Throughput
        row = f"  {cat.capitalize()+' throughput (QPS)':<35}"
        baseval = None
        for ph in phases:
            val = phase_results[ph].get(cat, {}).get("throughput_qps", None)
            if val is not None:
                row += f"  {val:>12.2f}"
                if baseval is None:
                    baseval = val
            else:
                row += f"  {'N/A':>12}"
        if baseval and baseval > 0:
            for ph in phases[1:]:
                val = phase_results[ph].get(cat, {}).get("throughput_qps", None)
                if val is not None:
                    delta = ((val - baseval) / baseval) * 100
                    row += f"  {delta:>+9.1f}%"
        print(row)

    print_divider()


# ── Plots ─────────────────────────────────────────────────────────────── #

COLORS = ["#2196F3", "#4CAF50", "#FF5722"]  # Blue, Green, Orange-Red per phase
CATEGORIES = ["short", "medium", "complex"]


def plot_latency_boxplot(phase_results: dict[int, dict], out_dir: str) -> None:
    """Box plot of per-query mean latencies per category, grouped by phase."""
    phases = sorted(phase_results.keys())
    n_cats = len(CATEGORIES)
    n_phases = len(phases)

    fig, axes = plt.subplots(1, n_cats, figsize=(6 * n_cats, 5), sharey=False)
    if n_cats == 1:
        axes = [axes]

    fig.suptitle("Query Latency Distribution by Category", fontsize=14, fontweight="bold")

    for ax, cat in zip(axes, CATEGORIES):
        data_per_phase = []
        labels = []
        for ph in phases:
            per_query = phase_results[ph].get(cat, {}).get("per_query", [])
            if per_query:
                latencies = [q["mean_ms"] for q in per_query]
                data_per_phase.append(latencies)
                labels.append(f"Phase {ph}")

        if not data_per_phase:
            ax.set_visible(False)
            continue

        bp = ax.boxplot(
            data_per_phase,
            tick_labels=labels,
            patch_artist=True,
            medianprops=dict(color="black", linewidth=2),
        )
        for patch, color in zip(bp["boxes"], COLORS[:len(data_per_phase)]):
            patch.set_facecolor(color)
            patch.set_alpha(0.7)

        ax.set_title(f"{cat.capitalize()} Queries", fontsize=12)
        ax.set_ylabel("Mean Latency (ms)")
        ax.set_xlabel("Phase")
        ax.yaxis.set_major_formatter(ticker.FormatStrFormatter("%.3f"))
        ax.grid(axis="y", linestyle="--", alpha=0.5)

    plt.tight_layout()
    path = os.path.join(out_dir, "latency_boxplot.png")
    plt.savefig(path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Plot: {path}")


def plot_throughput_bar(phase_results: dict[int, dict], out_dir: str) -> None:
    """Grouped bar chart of throughput (QPS) per category per phase."""
    phases = sorted(phase_results.keys())
    n_cats = len(CATEGORIES)
    x = np.arange(n_cats)
    width = 0.8 / len(phases)

    fig, ax = plt.subplots(figsize=(9, 5))
    fig.suptitle("Throughput by Category and Phase", fontsize=14, fontweight="bold")

    for i, (ph, color) in enumerate(zip(phases, COLORS)):
        qps_vals = []
        for cat in CATEGORIES:
            qps = phase_results[ph].get(cat, {}).get("throughput_qps", 0)
            qps_vals.append(qps)
        offset = (i - len(phases) / 2 + 0.5) * width
        bars = ax.bar(x + offset, qps_vals, width * 0.9, label=f"Phase {ph}",
                      color=color, alpha=0.8)
        for bar in bars:
            h = bar.get_height()
            if h > 0:
                ax.text(bar.get_x() + bar.get_width() / 2, h + 0.5,
                        f"{h:.0f}", ha="center", va="bottom", fontsize=8)

    ax.set_xticks(x)
    ax.set_xticklabels([c.capitalize() for c in CATEGORIES])
    ax.set_ylabel("Queries per Second (QPS)")
    ax.set_xlabel("Query Category")
    ax.legend()
    ax.grid(axis="y", linestyle="--", alpha=0.5)

    plt.tight_layout()
    path = os.path.join(out_dir, "throughput_bar.png")
    plt.savefig(path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Plot: {path}")


def plot_phase_comparison(phase_results: dict[int, dict], out_dir: str) -> None:
    """Grouped bar chart comparing mean and p99 latency across phases."""
    phases = sorted(phase_results.keys())
    if len(phases) < 2:
        return

    metrics = [("mean", "Mean Latency (ms)"), ("p99", "p99 Latency (ms)")]

    for metric, ylabel in metrics:
        fig, axes = plt.subplots(1, len(CATEGORIES), figsize=(5 * len(CATEGORIES), 5),
                                 sharey=False)
        if len(CATEGORIES) == 1:
            axes = [axes]
        fig.suptitle(f"Phase Comparison — {ylabel}", fontsize=14, fontweight="bold")

        for ax, cat in zip(axes, CATEGORIES):
            vals = []
            labels = []
            for ph in phases:
                v = phase_results[ph].get(cat, {}).get("latency_ms", {}).get(metric, None)
                if v is not None:
                    vals.append(v)
                    labels.append(f"Phase {ph}")

            if not vals:
                ax.set_visible(False)
                continue

            bars = ax.bar(labels, vals, color=COLORS[:len(vals)], alpha=0.8)
            for bar, v in zip(bars, vals):
                ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.0001,
                        f"{v:.4f}", ha="center", va="bottom", fontsize=8)

            ax.set_title(f"{cat.capitalize()} Queries", fontsize=11)
            ax.set_ylabel(ylabel)
            ax.yaxis.set_major_formatter(ticker.FormatStrFormatter("%.4f"))
            ax.grid(axis="y", linestyle="--", alpha=0.5)

        plt.tight_layout()
        safe_metric = metric.replace(" ", "_")
        path = os.path.join(out_dir, f"comparison_{safe_metric}.png")
        plt.savefig(path, dpi=150, bbox_inches="tight")
        plt.close()
        print(f"  Plot: {path}")


def plot_speedup_curve(phase_results: dict[int, dict], out_dir: str) -> None:
    """Speedup relative to Phase 1 baseline, per query category."""
    phases = sorted(phase_results.keys())
    baseline = phases[0]
    if len(phases) < 2:
        return

    fig, ax = plt.subplots(figsize=(8, 5))
    fig.suptitle(f"Speedup vs Phase {baseline} Baseline", fontsize=14, fontweight="bold")

    for cat, color in zip(CATEGORIES, ["#2196F3", "#4CAF50", "#FF5722"]):
        base_val = phase_results[baseline].get(cat, {}).get("latency_ms", {}).get("median", None)
        if base_val is None or base_val == 0:
            continue

        speedups = []
        for ph in phases:
            v = phase_results[ph].get(cat, {}).get("latency_ms", {}).get("median", None)
            speedups.append(base_val / v if v and v > 0 else 0)

        ax.plot(phases, speedups, marker="o", label=cat.capitalize(),
                color=color, linewidth=2, markersize=8)
        for ph, sp in zip(phases, speedups):
            ax.annotate(f"{sp:.2f}×", (ph, sp),
                        textcoords="offset points", xytext=(6, 4), fontsize=9)

    ax.axhline(y=1.0, color="gray", linestyle="--", alpha=0.6, label="Baseline (1.0×)")
    ax.set_xticks(phases)
    ax.set_xticklabels([f"Phase {p}" for p in phases])
    ax.set_ylabel("Speedup (×)")
    ax.set_xlabel("Phase")
    ax.legend()
    ax.grid(linestyle="--", alpha=0.4)
    ax.yaxis.set_major_formatter(ticker.FormatStrFormatter("%.2f"))

    plt.tight_layout()
    path = os.path.join(out_dir, "speedup_curve.png")
    plt.savefig(path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Plot: {path}")


# ── Argument parsing ──────────────────────────────────────────────────── #

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Aggregate benchmark results and produce plots")
    p.add_argument("--results-dir", default="benchmark/results",
                   help="Root results directory (default: benchmark/results)")
    p.add_argument("--phases", nargs="+", type=int, default=[1],
                   help="Phase numbers to include (default: 1)")
    p.add_argument("--output-dir", default="benchmark/results/plots",
                   help="Output directory for plots (default: benchmark/results/plots)")
    return p.parse_args()


# ── Entry point ───────────────────────────────────────────────────────── #

def main() -> None:
    args = parse_args()

    os.makedirs(args.output_dir, exist_ok=True)

    # Load results for all requested phases
    phase_results: dict[int, dict] = {}
    for ph in args.phases:
        results = load_phase_results(args.results_dir, ph)
        if results:
            phase_results[ph] = results
        else:
            print(f"Warning: no results found for phase {ph}")

    if not phase_results:
        print("Error: no results loaded", file=sys.stderr)
        sys.exit(1)

    # Print per-phase summaries
    for ph, results in sorted(phase_results.items()):
        print_phase_summary(ph, results)

    # Print cross-phase comparison
    if len(phase_results) > 1:
        print_comparison_table(phase_results)

    # Produce plots
    print("\n── Generating Plots ────────────────────────────────────────")
    plot_latency_boxplot(phase_results, args.output_dir)
    plot_throughput_bar(phase_results, args.output_dir)
    plot_phase_comparison(phase_results, args.output_dir)
    plot_speedup_curve(phase_results, args.output_dir)

    print("\nDone.\n")


if __name__ == "__main__":
    main()
