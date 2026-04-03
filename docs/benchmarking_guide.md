# Query Engine — Benchmarking & Profiling Guide

**Project:** Query Optimization System with Parallelization and Sharded Indexing  
**Scope:** Phases 1, 2, and 3  
**Author:** Vedant Keshav Jadhav  
**Date:** April 2026

---

## Table of Contents

1. [What is Benchmarking and Profiling?](#1-what-is-benchmarking-and-profiling)
2. [Why This Matters for the Project](#2-why-this-matters-for-the-project)
3. [Metrics We Are Measuring](#3-metrics-we-are-measuring)
4. [Methodology](#4-methodology)
5. [Benchmark Framework Directory Structure](#5-benchmark-framework-directory-structure)
6. [Script Responsibilities](#6-script-responsibilities)
7. [C++ Engine Interface for Benchmarking](#7-c-engine-interface-for-benchmarking)
8. [Measurement Protocol](#8-measurement-protocol)
9. [Results File Format](#9-results-file-format)
10. [Tooling Reference](#10-tooling-reference)
11. [Corpus and Query Workload](#11-corpus-and-query-workload)
12. [Reporting](#12-reporting)
13. [Action Plan](#13-action-plan)
14. [Phase Portability](#14-phase-portability)
15. [Common Mistakes to Avoid](#15-common-mistakes-to-avoid)

---

## 1. What is Benchmarking and Profiling?

These are two distinct but complementary activities. If you have never done either before, start here.

### Benchmarking
Benchmarking answers the question: **how fast and how resource-efficient is the system?**

It gives you concrete, comparable numbers — timing, memory usage, throughput — that you can record, report, and compare across different versions of the system. Benchmarking is always done from the *outside* of the system. You are measuring observable behaviour, not internal details.

Examples of benchmark questions:
- How long does it take to process the corpus and write the index file?
- How long does the engine take to load the index at startup?
- How many queries can the engine handle per second?
- How much memory does the engine use at peak?

### Profiling
Profiling answers the question: **where inside the system is time being spent?**

It gives you a breakdown of execution time at the function or even line level. Profiling is done to understand *why* benchmark numbers are what they are, and to find bottlenecks. Profiling is always done from the *inside* of the system — you attach a profiler to the running process.

Examples of profiling questions:
- Which function in the Python pipeline is slowest?
- Is the C++ query engine spending most of its time in decompression or in set operations?
- Are there unexpected cache misses slowing down the index lookup?

### The relationship between the two
Benchmark first. Profile when the benchmark reveals a problem or when you want to understand a result more deeply. Do not profile everything blindly — it generates too much noise.

---

## 2. Why This Matters for the Project

This project has three phases, each introducing a specific architectural change:

| Phase | Change | Question Being Answered |
|---|---|---|
| Phase 1 | Baseline single-process engine | What is the baseline performance? |
| Phase 2 | Sharded index | Does sharding the index improve query performance? |
| Phase 3 | Parallel query execution | Does parallelising across cores improve throughput and latency? |

The entire value of Phase 2 and Phase 3 depends on having clean, credible Phase 1 benchmark numbers as a baseline. If the benchmark methodology is flawed, the comparisons across phases are meaningless.

**The benchmark framework must be designed before any phase is implemented**, so that results are collected consistently from the start.

---

## 3. Metrics We Are Measuring

### 3.1 Time Metrics

There are three distinct time measurements, and they must be kept separate:

#### Indexing Time
- **What:** Time for the Python pipeline to read the corpus, build the inverted index, and write `index.bin` to disk.
- **Why:** Establishes the cost of the preprocessing step. Relevant for understanding how sharding affects index construction in Phase 2.
- **Unit:** Milliseconds (ms) or seconds (s) depending on corpus size.

#### Init Time (Engine Load Time)
- **What:** Time for the C++ engine to mmap the `index.bin` file, decompress it, and build the in-memory index structure — i.e., the time from `engine.init()` being called to the engine being ready to serve queries.
- **Why:** Critical for understanding startup cost. `mmap` should make this fast; the benchmark will verify this.
- **Unit:** Milliseconds (ms).

#### Query Latency
- **What:** Time for the engine to process a single query — from raw query string input to result doc IDs output. This excludes init time.
- **Why:** Measures responsiveness. The primary metric for comparing phases.
- **Unit:** Milliseconds (ms) or microseconds (µs) for fast queries.

### 3.2 Throughput

- **What:** Number of queries the engine can process per second over a large batch.
- **Why:** Latency measures one query at a time. Throughput measures sustained capacity. Parallelism in Phase 3 is expected to significantly improve throughput.
- **Unit:** Queries per second (QPS).
- **How to compute:** `total_queries / total_time_seconds`

### 3.3 Memory Metrics

#### Peak Memory During Indexing (Python)
- **What:** Maximum memory allocated by the Python pipeline during index construction.
- **Why:** Corpus processing can be memory-intensive. Useful for understanding scalability.
- **Unit:** Megabytes (MB).
- **Tool:** `tracemalloc` (Python standard library).

#### Peak Resident Set Size of C++ Engine
- **What:** Maximum physical memory used by the C++ engine process at runtime.
- **Why:** The in-memory inverted index can be large. This tells you the true memory footprint of the engine.
- **Unit:** Megabytes (MB).
- **Tool:** `/usr/bin/time -v` (Linux) or `\time -l` (macOS).

### 3.4 Index Size on Disk

- **What:** Size of `index.bin` in megabytes.
- **Why:** Directly reflects compression effectiveness. Comparing index sizes across phases (e.g., multiple shard files in Phase 2 vs one file in Phase 1) is informative.
- **Unit:** Megabytes (MB).

### 3.5 Metric Summary by Phase

| Metric | Phase 1 | Phase 2 | Phase 3 |
|---|---|---|---|
| Indexing time | Baseline | Compare | Compare |
| Init / load time | Baseline | Compare | Compare |
| Query latency | Baseline | Compare | Compare |
| Query throughput | Baseline | Compare | Compare |
| Peak memory (Python) | Baseline | Compare | Compare |
| Peak memory (C++) | Baseline | Compare | Compare |
| Index size on disk | Baseline | Compare | — |

---

## 4. Methodology

### 4.1 The Golden Rule: Never Measure a Single Run

A single timing measurement is unreliable. It is polluted by:
- OS scheduler interrupts
- CPU cache cold starts
- Disk I/O variance
- Background processes

**Always repeat each measurement multiple times and report statistical summaries.**

### 4.2 Statistical Summary — What to Report

For every timing measurement, report all of the following:

| Statistic | What it tells you |
|---|---|
| **Mean** | Average performance |
| **Median** | Typical performance, robust to outliers |
| **p95** | 95th percentile — worst case for 95% of queries |
| **p99** | 99th percentile — captures tail latency |
| **Min** | Best case |
| **Max** | Worst case / worst outlier |

> **Why median over mean?** A single slow run caused by an OS interrupt can inflate the mean significantly. The median is more representative of typical performance.

> **Why p99?** In any real system, tail latency matters. A query that is slow 1% of the time is still a problem. Phase 3 parallelism should reduce p99 noticeably — the benchmark will show this.

### 4.3 Warmup Runs

Before measuring, always run a warmup batch of queries. Warmup:
- Populates the CPU cache with the index data
- Stabilises OS memory state
- Eliminates cold-start effects from the first few queries

**Protocol:** Run 10 warmup queries, discard their times, then begin measuring.

### 4.4 Controlled Query Workload

Use a fixed, repeatable set of queries across all phases. Do not randomly generate queries at benchmark time. The same query files are used for Phase 1, 2, and 3.

Three query categories:

| Category | Description | Example |
|---|---|---|
| Short | Single term | `retrieval` |
| Medium | Two terms, one operator | `information AND retrieval` |
| Complex | Multiple terms and operators | `information AND retrieval NOT theory OR indexing` |

Recommended workload size: **100–500 queries** per category, 300–1500 total.

### 4.5 Corpus Scale

Test on two corpus sizes:

| Corpus | Size | Purpose |
|---|---|---|
| Small | ~5,000 documents | Sanity checking, fast iteration, debugging |
| Large | 100,000+ documents | Where sharding and parallelism show real impact |

Run all benchmarks on both corpus sizes and report separately. The interesting results will come from the large corpus.

### 4.6 Isolating What You Measure

Each measurement must isolate one thing:

- **Indexing time:** Start timer before pipeline runs, stop after `index.bin` is written. Do not include query time.
- **Init time:** Start timer at `engine.init()`, stop when engine is ready. Do not include any query.
- **Query latency:** Start timer after engine is fully initialised, stop after result is returned. One query at a time.
- **Throughput:** Submit all queries in the batch, measure total wall time, divide.

---

## 5. Benchmark Framework Directory Structure

```
benchmark/
├── queries/
│   ├── short.txt           # Single term queries, one per line
│   ├── medium.txt          # Two term queries with one operator, one per line
│   └── complex.txt         # Multi-operator queries, one per line
│
├── corpus/
│   ├── small/              # Small test corpus (~5,000 docs)
│   └── large/              # Full scale corpus (100,000+ docs)
│
├── scripts/
│   ├── bench_indexing.py   # Benchmarks Python pipeline (indexing time + memory)
│   ├── bench_init.py       # Benchmarks C++ engine init/load time
│   ├── bench_query.py      # Benchmarks query latency and throughput
│   └── bench_memory.sh     # Shell wrapper for /usr/bin/time -v (C++ memory)
│
├── results/
│   ├── phase1/             # All Phase 1 result JSON files
│   ├── phase2/             # All Phase 2 result JSON files
│   └── phase3/             # All Phase 3 result JSON files
│
└── report.py               # Aggregates results → summary tables and plots
```

All query files are plain text, one query per line. All result files are JSON. This keeps everything portable and human-readable.

---

## 6. Script Responsibilities

### `bench_indexing.py`

**What it measures:** Python pipeline performance — corpus processing and `index.bin` creation.

**How it works:**
1. Takes `--corpus`, `--output`, `--runs N` as CLI arguments
2. For each run:
   - Starts `tracemalloc` for memory tracking
   - Records `time.perf_counter()` start
   - Runs the pipeline
   - Records `time.perf_counter()` end
   - Records peak memory from `tracemalloc`
   - Records `index.bin` file size from disk
3. Computes statistics across N runs
4. Writes results to `results/phaseN/indexing_TIMESTAMP.json`

**Example usage:**
```bash
python3 benchmark/scripts/bench_indexing.py \
  --corpus benchmark/corpus/large \
  --output index.bin \
  --runs 10 \
  --phase 1
```

---

### `bench_init.py`

**What it measures:** C++ engine startup time — mmap, decompress, index construction.

**How it works:**
1. Takes `--engine`, `--index`, `--runs N` as CLI arguments
2. For each run:
   - Invokes the engine binary with `--bench-init` flag as a subprocess
   - Engine internally times `engine.init()` using `std::chrono` and prints elapsed time to stdout
   - Script captures stdout and records the time
3. Computes statistics across N runs
4. Writes results to `results/phaseN/init_TIMESTAMP.json`

**Example usage:**
```bash
python3 benchmark/scripts/bench_init.py \
  --engine ./build/engine \
  --index index.bin \
  --runs 20 \
  --phase 1
```

---

### `bench_query.py`

**What it measures:** Query latency and throughput.

**How it works:**
1. Takes `--engine`, `--index`, `--queries`, `--warmup N`, `--runs M`, `--phase` as CLI arguments
2. Launches the engine as a persistent subprocess in `--interactive` mode (stdin/stdout loop)
3. Warmup phase: sends N warmup queries, discards timing
4. Measurement phase: for each query, sends it M times, records round-trip time per query using `time.perf_counter()`
5. Computes per-query and aggregate statistics
6. Computes throughput: total queries processed / total time
7. Writes results to `results/phaseN/query_TIMESTAMP.json`

**Example usage:**
```bash
python3 benchmark/scripts/bench_query.py \
  --engine ./build/engine \
  --index index.bin \
  --queries benchmark/queries/complex.txt \
  --warmup 10 \
  --runs 50 \
  --phase 1
```

---

### `bench_memory.sh`

**What it measures:** Peak resident set size of the C++ engine process.

**How it works:**
Wraps `/usr/bin/time -v` (Linux) around the engine process and greps the `Maximum resident set size` field from the output.

```bash
#!/bin/bash
ENGINE=$1
INDEX=$2
OUTPUT=$3

/usr/bin/time -v $ENGINE --index $INDEX --bench-init 2>&1 \
  | grep "Maximum resident set size" \
  >> $OUTPUT
```

**Example usage:**
```bash
bash benchmark/scripts/bench_memory.sh \
  ./build/engine index.bin \
  benchmark/results/phase1/memory.txt
```

> On macOS, use `\time -l` instead of `/usr/bin/time -v` and look for `maximum resident set size`.

---

### `report.py`

**What it does:** Aggregates all JSON result files from a given phase and produces a unified summary.

**Outputs:**
- A printed summary table (mean, median, p99 for all metrics)
- Optionally, comparison tables across phases (if results from multiple phases exist)
- Optionally, plots using `matplotlib`:
  - Latency distribution (histogram or box plot)
  - Phase comparison bar chart (Phase 1 vs 2 vs 3)
  - Throughput comparison

**Example usage:**
```bash
python3 benchmark/report.py --phase 1
python3 benchmark/report.py --compare 1 2 3   # cross-phase comparison
```

---

## 7. C++ Engine Interface for Benchmarking

The C++ engine binary must expose the following CLI flags to support the benchmark scripts:

| Flag | Purpose |
|---|---|
| `--index <path>` | Path to `index.bin` (or shard directory in Phase 2/3) |
| `--bench-init` | Init-only mode: load index, print init time in ms to stdout, exit |
| `--interactive` | Enter stdin/stdout query loop (default query mode) |
| `--warmup <N>` | Process N warmup queries before the engine signals ready |

### stdin/stdout Query Protocol

In `--interactive` mode, the engine:
1. Prints `READY` to stdout when fully initialised
2. Reads one query per line from stdin
3. Prints result doc IDs (space-separated) followed by a newline to stdout
4. Repeats until EOF or `EXIT` command

The benchmark script (`bench_query.py`) uses this protocol to drive the engine as a persistent subprocess, measuring only the query round-trip time — not init time.

### `--bench-init` Output Format

When run with `--bench-init`, the engine prints exactly one line to stdout:
```
INIT_TIME_MS: 142.37
```
The benchmark script parses this value.

### Why stdin/stdout and not a socket or REST API?

For academic scale benchmarking, stdin/stdout is simpler, requires no networking setup, and has negligible overhead compared to the operations being measured. It also works identically across Phase 1, 2, and 3.

---

## 8. Measurement Protocol

This is the exact procedure to follow every time you run a benchmark. Follow it consistently across all phases.

```
BENCHMARK RUN PROCEDURE
═══════════════════════

BEFORE RUNNING:
  [ ] Close unnecessary background applications
  [ ] Plug in your laptop (power mode affects CPU frequency)
  [ ] Note the corpus being used (small / large)
  [ ] Note the query file being used (short / medium / complex)
  [ ] Note compiler flags used for C++ binary (always use -O2)

INDEXING BENCHMARK (bench_indexing.py):
  [ ] Run with --runs 10
  [ ] Record: mean, median, p99, min, max of indexing time
  [ ] Record: peak memory (MB)
  [ ] Record: index.bin size on disk (MB)

INIT BENCHMARK (bench_init.py):
  [ ] Run with --runs 20
  [ ] Record: mean, median, p99, min, max of init time

MEMORY BENCHMARK (bench_memory.sh):
  [ ] Run once
  [ ] Record: peak resident set size (MB)

QUERY BENCHMARK (bench_query.py):
  [ ] Run with --warmup 10 --runs 50
  [ ] Run separately for: short.txt, medium.txt, complex.txt
  [ ] Record per query set: mean, median, p95, p99, min, max latency
  [ ] Record: throughput (QPS) for each query set

AFTER RUNNING:
  [ ] Verify JSON files written to results/phaseN/
  [ ] Run report.py to check output looks sane
  [ ] Commit results to version control
```

---

## 9. Results File Format

Every script writes a structured JSON file. JSON was chosen for portability, human readability, and easy parsing by `report.py`.

### Naming Convention
```
results/phase1/indexing_20260402_1000.json
results/phase1/init_20260402_1001.json
results/phase1/query_complex_20260402_1002.json
```

### Full Schema

```json
{
  "phase": 1,
  "timestamp": "2026-04-02T10:00:00",
  "corpus": "large",
  "query_set": "complex",
  "warmup_queries": 10,
  "repetitions": 50,
  "system": {
    "cpu": "Intel Core i7-12700H",
    "cores": 14,
    "ram_gb": 16,
    "os": "Ubuntu 22.04",
    "compiler": "g++ -O2 -std=c++17",
    "python_version": "3.11"
  },
  "indexing": {
    "time_ms": {
      "mean": 0.0,
      "median": 0.0,
      "p95": 0.0,
      "p99": 0.0,
      "min": 0.0,
      "max": 0.0
    },
    "peak_memory_mb": 0.0,
    "index_size_mb": 0.0
  },
  "init": {
    "time_ms": {
      "mean": 0.0,
      "median": 0.0,
      "p95": 0.0,
      "p99": 0.0,
      "min": 0.0,
      "max": 0.0
    },
    "peak_memory_mb": 0.0
  },
  "query": {
    "latency_ms": {
      "mean": 0.0,
      "median": 0.0,
      "p95": 0.0,
      "p99": 0.0,
      "min": 0.0,
      "max": 0.0
    },
    "throughput_qps": 0.0
  }
}
```

Fields not applicable to a given script run can be left as `null`.

---

## 10. Tooling Reference

### Python Side

| Tool | Purpose | How to use |
|---|---|---|
| `time.perf_counter()` | High resolution wall clock timing | `start = time.perf_counter()` ... `elapsed = time.perf_counter() - start` |
| `tracemalloc` | Peak memory tracking inside Python | `tracemalloc.start()` ... `current, peak = tracemalloc.get_traced_memory()` |
| `cProfile` | Function-level profiling | `python3 -m cProfile -o out.prof pipeline.py` then `snakeviz out.prof` to visualise |
| `statistics` | Computing mean, median, stdev | Standard library, no install needed |
| `numpy` | Computing percentiles (p95, p99) | `numpy.percentile(times, 99)` |
| `subprocess` | Driving the C++ engine | `proc = subprocess.Popen(...)` |

### C++ Side

| Tool | Purpose | How to use |
|---|---|---|
| `std::chrono::high_resolution_clock` | Nanosecond resolution timing | `auto t0 = chrono::high_resolution_clock::now()` |
| `/usr/bin/time -v` | Peak resident set size | `\time -v ./engine 2>&1 \| grep "Maximum resident"` |
| `valgrind --tool=callgrind` | Deep function-level profiling | `valgrind --tool=callgrind ./engine` then `kcachegrind callgrind.out.*` |
| `perf stat` | Hardware performance counters | `perf stat ./engine` — shows cache misses, branch mispredictions |
| `perf record / perf report` | Sampling profiler | `perf record ./engine` then `perf report` |

### Compiler Flags

Always compile the C++ engine with:
```
g++ -O2 -std=c++17
```

Never benchmark a debug build (`-O0`). Always note the exact flags in the system field of the JSON result.

---

## 11. Corpus and Query Workload

### Recommended Corpora

| Corpus | Size | Source | Notes |
|---|---|---|---|
| Small synthetic | ~5,000 docs | Generate or use Gutenberg subset | For fast iteration and debugging |
| Wikipedia dump | 1M+ articles | [dumps.wikimedia.org](https://dumps.wikimedia.org) | Standard, clean, realistic |
| TREC collections | Varies | TREC website | Standard in IR research |
| Project Gutenberg | ~60,000 books | [gutenberg.org](https://www.gutenberg.org) | Free, plaintext, easy to parse |

### Query File Format

Plain text, one query per line:

```
# short.txt
retrieval
information
indexing
compression
query

# medium.txt
information AND retrieval
index AND compression
query OR search
boolean NOT ranking

# complex.txt
information AND retrieval NOT theory
index AND compression OR encoding NOT binary
query AND boolean NOT ranking OR evaluation
```

Lines starting with `#` are comments and should be skipped by the benchmark scripts.

### Query Set Size

| Category | Minimum | Recommended |
|---|---|---|
| Short | 50 | 200 |
| Medium | 50 | 200 |
| Complex | 50 | 100 |

---

## 12. Reporting

### What to Include in the Final Benchmark Report

For each phase, the report should include:

**System Information**
- CPU model and core count
- RAM (GB)
- OS and version
- Compiler and flags
- Python version

**Corpus Information**
- Corpus name
- Number of documents
- Total size on disk (uncompressed)

**Index Information**
- `index.bin` size on disk
- Number of unique terms indexed
- Average posting list length

**Results Tables**
One table per metric, showing mean / median / p99 / min / max.

**Cross-Phase Comparison Table** (after all phases complete)

| Metric | Phase 1 | Phase 2 | Phase 3 | P2 vs P1 | P3 vs P1 |
|---|---|---|---|---|---|
| Query latency median (ms) | — | — | — | — | — |
| Query throughput (QPS) | — | — | — | — | — |
| Init time median (ms) | — | — | — | — | — |
| Peak memory C++ (MB) | — | — | — | — | — |

### Plots (via `report.py` + `matplotlib`)

- Latency distribution: box plot or histogram per query category
- Phase comparison: grouped bar chart for latency and throughput
- Throughput scaling: line chart across phases

---

## 13. Action Plan

Follow this checklist in order.

### Phase 1 Benchmarking Setup

```
[ ] 1. Create benchmark/ directory structure as specified
[ ] 2. Write queries/short.txt, queries/medium.txt, queries/complex.txt
[ ] 3. Prepare corpus/small/ and corpus/large/
[ ] 4. Implement bench_indexing.py
[ ] 5. Implement bench_init.py
[ ] 6. Implement bench_query.py
[ ] 7. Implement bench_memory.sh
[ ] 8. Add --bench-init and --interactive flags to C++ engine
[ ] 9. Implement READY / stdin / stdout query protocol in C++ engine
[ ] 10. Run full benchmark suite on Phase 1 engine
[ ] 11. Verify JSON results written correctly
[ ] 12. Implement report.py and generate Phase 1 summary
[ ] 13. Commit results and scripts to version control
```

### Phase 2 and 3

```
[ ] 14. Reuse all query files unchanged
[ ] 15. Point scripts at new engine binary
[ ] 16. Write results to results/phase2/ and results/phase3/
[ ] 17. Run report.py --compare 1 2 3 for cross-phase summary
```

---

## 14. Phase Portability

The benchmark framework is designed to work across all three phases without modification to the scripts or query files. The only things that change between phases are:

| What changes | Phase 1 → Phase 2 | Phase 2 → Phase 3 |
|---|---|---|
| Engine binary | Same binary, different index | Same binary, parallel execution |
| Index file | Single `index.bin` | Multiple shard `.bin` files |
| `--index` flag value | Path to single file | Path to shard directory |
| Results directory | `results/phase1/` | `results/phase2/`, `results/phase3/` |

The scripts, query files, measurement protocol, and JSON schema stay identical across all phases. This is intentional — it ensures the comparisons are valid.

---

## 15. Common Mistakes to Avoid

| Mistake | Why it matters | What to do instead |
|---|---|---|
| Measuring only one run | Single run is noisy and unreliable | Always repeat 10–50 times and report statistics |
| Measuring init time and query time together | You cannot separate their contributions | Measure them independently with separate scripts |
| Benchmarking a debug build | `-O0` code is 3–10x slower than `-O2` | Always use `-O2` and record compiler flags |
| Using different queries across phases | Makes phase comparisons invalid | Use the same fixed query files for all phases |
| Not warming up | Cold cache inflates first few query times | Always run 10 warmup queries before measuring |
| Reporting only mean | Outliers can make mean misleading | Always report median and p99 alongside mean |
| Running benchmarks with other apps open | Background load adds noise | Close unnecessary applications before benchmarking |
| Not recording system specs | Results are not reproducible or comparable | Always record CPU, RAM, OS, compiler in JSON |
| Changing corpus between phases | Invalid comparison | Use the exact same corpus files for all phases |
| Not committing results to version control | Results get lost or overwritten | Commit all JSON result files after each benchmark run |
