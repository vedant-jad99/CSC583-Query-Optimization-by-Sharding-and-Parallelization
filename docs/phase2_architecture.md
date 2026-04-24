# Query Engine — Phase 2 Architecture & Unit Design

**Project:** Query Optimization System with Parallelization and Sharded Indexing  
**Phase:** 2 — Sharded Index  
**Author:** Vedant Keshav Jadhav  
**Date:** April 2026

---

## Table of Contents

1. [Phase 2 Objective](#1-phase-2-objective)
2. [Decision Record](#2-decision-record)
3. [What Changes from Phase 1](#3-what-changes-from-phase-1)
4. [Part 1 — Python Sharding Pipeline](#4-part-1--python-sharding-pipeline)
5. [Part 2 — C++ Query Engine](#5-part-2--c-query-engine)
6. [Complete Architecture Diagram](#6-complete-architecture-diagram)
7. [Data Flow Summary](#7-data-flow-summary)
8. [Key Design Decisions Table](#8-key-design-decisions-table)
9. [Benchmarking Additions for Phase 2](#9-benchmarking-additions-for-phase-2)
10. [Implementer Checklist](#10-implementer-checklist)

---

## 1. Phase 2 Objective

Phase 1 established a baseline single-process Boolean query engine — one index, one query runner, one `.bin` file. The benchmark numbers from Phase 1 are the ground truth.

Phase 2 introduces **document-based index sharding**. The corpus is partitioned across N shards at build time, each shard producing its own complete `.bin` file. The C++ query engine loads all N shards and queries them sequentially, merging results before returning.

**The single variable being introduced in Phase 2 is sharding.** Query execution remains sequential — no parallelism is added yet. This isolation is deliberate: it allows the benchmark to attribute any performance delta specifically to the effect of smaller, sharded indexes rather than to parallelism.

**Expected gains from sharding:**
- Each shard's posting lists are a fraction of full-corpus size → faster Boolean set operations
- Smaller in-memory index per shard → better CPU cache utilisation
- Index build time is parallelised across processes → faster preprocessing

**Phase 3 will add parallel query execution** — querying all N shards concurrently across threads. The Phase 2 architecture is designed specifically so that Phase 3 requires minimal structural change.

---

## 2. Decision Record

Every significant design decision made during Phase 2 scoping is recorded here with full rationale.

---

### Decision 1 — Document-based sharding over term-based sharding

**Term-based sharding:** The vocabulary is partitioned across shards. Each shard owns a subset of terms and stores posting lists for those terms covering the full corpus.

**Document-based sharding:** The corpus is partitioned across shards. Each shard owns a subset of documents and builds a complete index over those documents. Every query fans out to all shards.

| | Term-based | Document-based |
|---|---|---|
| Posting list size | Full corpus length | Fraction of corpus |
| Query fan-out | Targeted (only relevant shards) | All shards always |
| Shard balance | Uneven (high-freq terms dominate) | Even (by document count) |
| Build complexity | Higher (need full vocab first) | Lower (split docs, build independently) |
| NOT operation | Complex (universal set spans shards) | Clean (per-shard universal set) |
| Performance gain source | Vocabulary partitioning | Smaller posting lists |

**Decision: Document-based sharding.**

The performance story of this project is: smaller posting lists → faster Boolean set operations → lower query latency. Term-based sharding does not reduce posting list size. Document-based sharding directly reduces posting list length in proportion to the number of shards.

---

### Decision 2 — Global doc ID consistency via presorting

**The problem:** N independent pipeline processes each building their own index would re-enumerate doc IDs from 0, making merged results corrupt.

**Option A — Pre-hash filenames to IDs, save to JSON:** O(1) lookup but O(N) disk I/O overhead for write + read + parse. Slower in practice than sorting.

**Option B — Presort corpus files, assign IDs by position with shard offset:** O(N log N) in-memory, zero disk I/O.

**Decision: Option B.** O(N log N) in-memory is dramatically faster than O(N) disk I/O. No extra files. Globally unique doc IDs with zero coordination overhead between shard processes.

**Invariant:** The corpus file list must be sorted identically every time — by full file path, alphabetically.

---

### Decision 3 — Sharding at build time in Python, not at query time in C++

**Decision: Build-time sharding in Python.** Preserves the Python writes / C++ reads boundary. The engine loads pre-built shard files with no knowledge of sharding logic.

---

### Decision 4 — Shard count: CLI arg in C++, env var in Python, default 4

**C++ engine:** `--shards N` CLI argument parsed by `main.cpp`, forwarded to `BooleanEngine::init()` as a parameter. Explicit, scriptable, no env var leakage between benchmark runs.

**Python pipeline:** `N_SHARDS` environment variable read by `ShardBuilder`. Standard mechanism for Makefile-driven build steps.

**Default:** 4 — reflects realistic core count on a development laptop.

---

### Decision 5 — Parallel shard building via multiprocessing, not threading

Python's GIL prevents true parallelism for CPU-bound work (tokenization, stemming, encoding) using threads.

**Decision: `multiprocessing` via `concurrent.futures.ProcessPoolExecutor`.** Separate OS processes, each with its own GIL. True parallelism on separate cores. No locks or synchronisation needed between shard processes.

---

### Decision 6 — New class: ShardBuilder

New class `ShardBuilder` orchestrates the sharded build. Owns N `Pipeline` instances, manages `ProcessPoolExecutor`. Only new Python class in Phase 2. Build-time only — no C++ equivalent.

---

### Decision 7 — N QueryRunners in C++, one per shard

**Option A:** Single `QueryRunner` iterating over N indexes internally.

**Option B:** N `QueryRunner` instances, sequential execution, results merged after.

**Decision: Option B.** Phase 3 transition = one change: replace sequential iteration with concurrent `std::async`. `QueryRunner` and `IRSubsystem` require zero modification. Option A would require restructuring `IRSubsystem` for concurrent access.

---

### Decision 8 — Preprocessor moved to BooleanEngine

With N `QueryRunner` instances, keeping `Preprocessor` in `QueryRunner` would preprocess the same query N times identically. `Preprocessor` moved to `BooleanEngine` — preprocesses once, passes normalized terms to all N `QueryRunner`s. Implemented as Phase 1 amendment.

---

### Decision 9 — No ShardManager class; merge lives on BooleanEngine

`ShardManager` was considered as an intermediary. Rejected as unnecessary indirection. `BooleanEngine` is already the top-level coordinator and owns the merge responsibility directly.

---

### Decision 10 — Two merge strategies, switchable via CLI arg

**Pairwise merge:** Sequential two-way merge. O(M × N). Simple, correct, sufficient for small N.

**Priority queue k-way merge:** Min-heap merge. O(M log N). More efficient for large result sets.

**CLI argument:** `--merge-strategy PAIRWISE` or `--merge-strategy PRIORITY_QUEUE` passed to `run_engine`. `main.cpp` parses this and forwards `use_priority_queue` as a bool to `BooleanEngine::init()`. Default: `PAIRWISE`.

Both strategies are benchmarked separately — the delta is a project result in itself.

---

### Decision 11 — Conditional compilation via -DPHASE flag, two translation units

Rather than runtime detection of phase (which bloats the binary with unused code), the engine is compiled with `-DPHASE=N` injected by the Makefile via `CXXFLAGS`.

- `includes/boolean_engine.hpp` — single header with `#if PHASE == 1` / `#else` blocks
- `src/boolean_engine.cpp` — Phase 1 only, compiled when `PHASE=1`
- `src/boolean_engine_p2.cpp` — Phase 2 and 3, compiled when `PHASE>=2`. Phase 3 parallel fan-out via `std::async` lives in the same file under `#elif PHASE == 3`
- Makefile excludes the unused translation unit per phase via `filter-out`

Zero runtime overhead. One clean binary per phase.

---

## 3. What Changes from Phase 1

### Python — Changes

| Component | Status | Change |
|---|---|---|
| `FileReader` | Unchanged | — |
| `Tokenizer` | Unchanged | — |
| `Normalizer` and subclasses | Unchanged | — |
| `IndexBuilder` | Unchanged | — |
| `VBEncoder` | Unchanged | — |
| `BinWriter` | Unchanged | — |
| `MakeBinFile` | Unchanged | — |
| `IndexCreator` | Unchanged | — |
| `Pipeline` | **Amended in Phase 1** | Accepts `file_slice` and `doc_id_offset` |
| `pipeline.py` entry point | **Amended in Phase 1** | Adds `presort_corpus()` function |
| `ShardBuilder` | **New in Phase 2** | Owns N Pipelines, drives ProcessPoolExecutor |
| `main_sharded.py` | **New in Phase 2** | Phase 2 entry point, invokes ShardBuilder |

### C++ — Changes

| Component | Status | Change |
|---|---|---|
| `Decompressor` | Unchanged | — |
| `Preprocessor` | **Amended in Phase 1** | Moved to BooleanEngine |
| `OpHandler` | Unchanged | — |
| `IRSubsystem` | Unchanged | — |
| `QueryRunner` | **Modified in Phase 2** | Accepts normalized terms, not raw query |
| `boolean_engine_p2.cpp` | **New in Phase 2** | Phase 2/3 BooleanEngine: N Decompressors, N QueryRunners, merge |
| `main.cpp` | **Modified in Phase 2** | Parses `--shards` and `--merge-strategy`, forwards to `init()` |

---

## 4. Part 1 — Python Sharding Pipeline

### Class Hierarchy

```
main_sharded.py (Phase 2 entry point)
├── presort_corpus()              ← Phase 1 amendment, reused here
└── ShardBuilder                 ← Phase 2 new
    └── N × Pipeline             ← Phase 1 amended
            ├── IndexCreator
            │   ├── FileReader
            │   ├── Tokenizer
            │   ├── Normalizer
            │   │   ├── CaseFolder
            │   │   ├── PunctuationRemover
            │   │   ├── StopWordFilter
            │   │   └── Stemmer
            │   └── IndexBuilder
            └── MakeBinFile
                ├── VBEncoder
                └── BinWriter
```

---

### Unit Specifications

#### `presort_corpus(corpus_dir)` — Phase 1 Amendment, reused

Sorts all corpus files by full path alphabetically. Called once before `ShardBuilder`. Authoritative document ordering for the entire system.

```python
def presort_corpus(corpus_dir: str) -> list[str]:
    files = [
        os.path.join(corpus_dir, f)
        for f in os.listdir(corpus_dir)
        if os.path.isfile(os.path.join(corpus_dir, f))
    ]
    return sorted(files)
```

#### `Pipeline` — Phase 1 Amendment

Accepts `file_slice: list[str]` and `doc_id_offset: int`. Assigns IDs as `offset + local_index`. Phase 1 call: full file list, offset=0 — behaviour unchanged.

#### `ShardBuilder` — Phase 2 New

- **Reads:** `N_SHARDS` env var (default: 4)
- **Output:** `shards/shard_0.bin ... shards/shard_{N-1}.bin` (project root `shards/` directory, gitignored)

**Execution flow:**
```
1. Read N_SHARDS from environment (default 4)
2. presort_corpus() → sorted file list
3. Partition into N equal slices
4. offset_i = i × (total_docs // N_SHARDS)
5. ProcessPoolExecutor(max_workers=N)
6. Submit N: run_pipeline(file_slice_i, offset_i, shard_id_i)
7. Await all futures
8. Verify N .bin files written
```

**Worker function** (module-level — required for picklability):
```python
def run_pipeline(file_slice: list[str], offset: int, shard_id: int) -> None:
    pipeline = Pipeline(file_slice=file_slice, doc_id_offset=offset)
    pipeline.run(output_path=f"shards/shard_{shard_id}.bin")
```

### Build Integration — Phase 2

```makefile
index-builder: $(VENV)
ifeq ($(PHASE), 2)
    $(PYTHON) scripts/main_sharded.py --corpus data/corpus --out-dir shards/
endif
```

---

## 5. Part 2 — C++ Query Engine

### Class Hierarchy

```
main.cpp
└── BooleanEngine                    (boolean_engine_p2.cpp, compiled -DPHASE=2)
    ├── Preprocessor                 ← moved from QueryRunner (Phase 1 amendment)
    ├── vector<Decompressor>         ← N instances, one per shard
    ├── vector<QueryRunner>          ← N instances, one per shard
    │         └── IRSubsystem
    │               └── OpHandler
    └── do_merge()                   ← new (Phase 2)
          ├── pairwise_merge()       O(M×N)
          └── priority_queue_merge() O(M logN)
```

---

### Unit Specifications

#### `Decompressor` — Unchanged

N instances in `std::vector<Decompressor>`. Each loads one shard `.bin` via `mmap`. Identical to Phase 1.

#### `Preprocessor` — Phase 1 Amendment

Owned by `BooleanEngine`. Called once per query. Produces normalized terms for all N `QueryRunner`s.

#### `QueryRunner` — Modified in Phase 2

`runQuery()` accepts `const vector<string>& normalized_terms`. `Preprocessor` removed from ownership. All else unchanged.

#### `IRSubsystem` — Unchanged

Owns `OpHandler`. Holds const index and const doc ID set for its shard.

#### `OpHandler` — Unchanged

AND / OR / NOT as sorted list set operations.

#### `BooleanEngine` — New translation unit in Phase 2

- **Source:** `src/boolean_engine_p2.cpp` (compiled when `PHASE >= 2`)
- **Members:** `int n_shards`, `bool use_priority_queue`, `vector<Decompressor>`, `vector<QueryRunner>`
- **Receives at `init()` time:** `n_shards` and `use_priority_queue` as parameters from `main.cpp`

**`init(shard_dir, n_shards, use_priority_queue)`:**
```cpp
this->n_shards           = n_shards;
this->use_priority_queue = use_priority_queue;
decompressors.resize(n_shards);
queryRunners.resize(n_shards);

for (int i = 0; i < n_shards; i++) {
    decompressors[i].load(shard_dir + "/shard_" + to_string(i) + ".bin");
    queryRunners[i].initIRSystem(
        std::move(decompressors[i].getIndex()),
        std::move(decompressors[i].getDocIDs())
    );
}
```

**`query(const string& raw_query)`:**
```cpp
auto normalized = preprocessor.process(raw_query);   // once

vector<vector<uint32_t>> shard_results;
for (int i = 0; i < n_shards; i++) {
    shard_results.push_back(
        vector<uint32_t>(queryRunners[i].runQuery(normalized))
    );
}

return do_merge(shard_results);
```

#### `do_merge()` — Dispatch method

Dispatches to `pairwise_merge()` or `priority_queue_merge()` based on `use_priority_queue` bool set at init from `--merge-strategy` CLI arg.

**`pairwise_merge`:** Sequential two-way merge. O(M × N). Simple, correct, suitable for small N.

**`priority_queue_merge`:** Min-heap k-way merge. O(M log N). More efficient for large result sets.

#### `main.cpp` — Phase 2 CLI

```
./run_engine shards/ --shards 4 --merge-strategy PAIRWISE --interactive
./run_engine shards/ --shards 4 --merge-strategy PRIORITY_QUEUE --bench
./run_engine shards/ --shards 4 --bench-init
```

`main.cpp` parses `--shards N` (default 4) and `--merge-strategy` (default PAIRWISE) from `argv` and forwards them to `BooleanEngine::init()`.

---

## 6. Complete Architecture Diagram

```
╔══════════════════════════════════════════════════════════════════════════════════╗
║                      PHASE 2 — COMPLETE ARCHITECTURE                             ║
╚══════════════════════════════════════════════════════════════════════════════════╝

  BUILD TIME
 ┌──────────────────────────────────────────────────────────────────────────────┐
 │  PYTHON SHARDING PIPELINE                                                    │
 │                                                                              │
 │  main_sharded.py entry point                                                 │
 │  ┌────────────────────────────────────────────────────────────────────────┐  │
 │  │  presort_corpus(corpus_dir) → sorted file list                         │  │
 │  └─────────────────────────────────┬──────────────────────────────────────┘  │
 │                                    │                                         │
 │                                    ▼                                         │
 │  ┌─────────────────────────────────────────────────────────────────────────┐ │
 │  │  ShardBuilder                                                           │ │
 │  │                                                                         │ │
 │  │  reads N_SHARDS env var (default 4)                                     │ │
 │  │  partitions sorted file list into N slices                              │ │
 │  │  computes offsets: [0, 25000, 50000, 75000]                             │ │
 │  │                                                                         │ │
 │  │  ProcessPoolExecutor(max_workers=N)                                     │ │
 │  │  ├── Process 0: Pipeline(slice_0, offset=0)   → shards/shard_0.bin     │ │
 │  │  ├── Process 1: Pipeline(slice_1, offset=25k) → shards/shard_1.bin     │ │
 │  │  ├── Process 2: Pipeline(slice_2, offset=50k) → shards/shard_2.bin     │ │
 │  │  └── Process 3: Pipeline(slice_3, offset=75k) → shards/shard_3.bin     │ │
 │  └─────────────────────────────────────────────────────────────────────────┘ │
 │                                                                              │
 │  Each Pipeline (per Phase 1 design):                                         │
 │  FileReader → Tokenizer → Normalizer → IndexBuilder → VBEncoder → BinWriter  │
 │                                                                              │
 │  Makefile: $(PYTHON) scripts/main_sharded.py --corpus data/corpus            │
 │            --out-dir shards/                                                 │
 └──────────────────────────────────────────┬───────────────────────────────────┘
                                            │
                          ┌─────────────────┼─────────────────┐
                          │                 │                 │
                          ▼                 ▼                 ▼
           ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐
           │ shards/shard_0   │  │ shards/shard_1   │  │ shards/shard_2   │  ...
           │  docs 0-24999    │  │  docs 25k-49k    │  │  docs 50k-74k    │
           │  [Phase 1 format]│  │  [Phase 1 format]│  │  [Phase 1 format]│
           └──────┬───────────┘  └──────┬───────────┘  └──────┬───────────┘
                  │                     │                      │
  QUERY TIME      │   mmap ×N           │                      │
 ┌───────────────────────────────────────────────────────────────────────────┐
 │  C++ QUERY ENGINE  (-DPHASE=2, boolean_engine_p2.cpp)                     │
 │                    ▼                 ▼                      ▼             │
 │  ┌─────────────────────────────────────────────────────────────────────┐  │
 │  │  main.cpp                                                           │  │
 │  │  args: shards/ --shards 4 --merge-strategy PAIRWISE --bench        │  │
 │  │  engine.init("shards/", n_shards=4, use_priority_queue=false)      │  │
 │  └─────────────────────────────┬───────────────────────────────────────┘  │
 │                                │                                          │
 │                                ▼                                          │
 │  ┌─────────────────────────────────────────────────────────────────────┐  │
 │  │  BooleanEngine                                                      │  │
 │  │  n_shards=4, use_priority_queue=false  (from CLI, via main.cpp)     │  │
 │  │                                                                     │  │
 │  │  ┌─────────────┐                                                    │  │
 │  │  │ Preprocessor│  raw query → normalized terms (once per query)     │  │
 │  │  └─────────────┘                                                    │  │
 │  │                                                                     │  │
 │  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐              │  │
 │  │  │Decompressor 0│  │Decompressor 1│  │Decompressor 2│  ...         │  │
 │  │  │mmap shard_0  │  │mmap shard_1  │  │mmap shard_2  │              │  │
 │  │  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘              │  │
 │  │         │ std::move       │ std::move        │ std::move            │  │
 │  │         ▼                 ▼                  ▼                     │  │
 │  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐                 │  │
 │  │  │QueryRunner 0│  │QueryRunner 1│  │QueryRunner 2│  ...            │  │
 │  │  │IRSubsystem 0│  │IRSubsystem 1│  │IRSubsystem 2│                 │  │
 │  │  │ OpHandler   │  │ OpHandler   │  │ OpHandler   │                 │  │
 │  │  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘                 │  │
 │  │         │                │                 │                       │  │
 │  │     results_0        results_1         results_2  ...              │  │
 │  │         │                │                 │                       │  │
 │  │         └────────────────┴─────────────────┘                       │  │
 │  │                          │                                         │  │
 │  │                          ▼                                         │  │
 │  │  ┌────────────────────────────────────────────────────────────┐    │  │
 │  │  │  do_merge()  [dispatched by use_priority_queue bool]       │    │  │
 │  │  │  PAIRWISE:       O(M×N)    sequential two-way merge        │    │  │
 │  │  │  PRIORITY_QUEUE: O(M logN) k-way heap merge                │    │  │
 │  │  └────────────────────────────────────────────────────────────┘    │  │
 │  └─────────────────────────────────────────────────────────────────────┘  │
 │                                │                                          │
 │                                ▼                                          │
 │                   vector<uint32_t>  globally unique result doc IDs        │
 └────────────────────────────────────────────────────────────────────────────┘

 CONST CORRECTNESS CONTRACT (unchanged from Phase 1)
 ┌─────────────────────────────────────────────────────────────┐
 │  inverted index per shard    →  const unordered_map         │
 │  universal doc ID set        →  const set<uint32_t>         │
 │  posting list lookups        →  const vector<uint32_t>&     │
 │  OpHandler inputs            →  const vector<uint32_t>&     │
 │  per-shard query results     →  const vector<uint32_t>&     │
 └─────────────────────────────────────────────────────────────┘
```

---

## 7. Data Flow Summary

```
corpus/
  └── all docs      →  presort_corpus()  →  sorted file list
                    →  ShardBuilder partitions into N slices
                    →  N ProcessPoolExecutor workers (true parallelism)
                    →  Each: Pipeline (per Phase 1 design)
                    →  shards/shard_0.bin ... shards/shard_N.bin

shards/shard_i.bin  →  Decompressor_i (mmap)
                    →  unordered_map + set<uint32_t>
                    →  std::move → QueryRunner_i::IRSubsystem

raw query           →  Preprocessor (once, in BooleanEngine)
                    →  normalized terms
                    →  QueryRunner_0 ... QueryRunner_N (sequential)
                    →  results_0 ... results_N
                    →  do_merge() → final globally unique doc IDs
```

---

## 8. Key Design Decisions Table

| Decision | Choice | Rationale |
|---|---|---|
| Sharding strategy | Document-based | Smaller posting lists → faster set ops; clean benchmark variable |
| Doc ID consistency | Presort + offset | O(N log N) in-memory beats O(N) disk I/O; no extra files |
| Shard build location | Python build time | Preserves Python writes / C++ reads boundary |
| Shard count (C++) | CLI arg `--shards`, default 4 | Explicit, scriptable, no env var leakage between benchmark runs |
| Shard count (Python) | Env var `N_SHARDS`, default 4 | Standard for Makefile-driven build steps |
| Python parallelism | multiprocessing via ProcessPoolExecutor | True CPU parallelism; threads cannot due to GIL |
| C++ query structure | N QueryRunners sequential | Phase 3 transition = one change (sequential → concurrent) |
| Preprocessor location | BooleanEngine | Preprocess once per query; better separation of concerns |
| ShardManager | Not implemented | BooleanEngine is already the coordinator; no extra layer needed |
| Merge strategy | Pairwise + priority queue, `--merge-strategy` CLI arg | Benchmarkable experiment; explicit and scriptable |
| Conditional compilation | `-DPHASE=N` Makefile flag, two translation units | Zero runtime overhead; clean per-phase binary |
| Shard directory | `shards/` project root, gitignored | Clean separation from source; excluded from version control |

---

## 9. Benchmarking Additions for Phase 2

The Phase 1 benchmarking framework is reused entirely. The following additions are made:

### Passing CLI Args to Engine Subprocess

`bench_init.py` and `bench_query.py` need to forward `--shards N` and `--merge-strategy` to the engine subprocess. This will be implemented as a passthrough `--engine-args` flag on the benchmark scripts, or as explicit `--shards` and `--merge-strategy` flags mirrored directly.

### New Benchmark Dimension — Merge Strategy

Run the full benchmark suite twice for Phase 2 — once with PAIRWISE, once with PRIORITY_QUEUE. Results written to separate subdirectories:

```
results/
├── phase1/
├── phase2/
│   ├── pairwise/
│   └── priority_queue/
└── phase3/
```

### Cross-Phase Comparison

`report.py --phases 1 2` produces:
- Latency delta: Phase 1 vs Phase 2 pairwise vs Phase 2 priority queue
- Throughput delta across phases and merge strategies
- Speedup curve showing Phase 2 gain from smaller posting lists

---

## 10. Implementer Checklist

### Python

```
[ ] presort_corpus() in pipeline.py (Phase 1 amendment — already done)
[ ] Pipeline accepts file_slice and doc_id_offset (already done)
[ ] ShardBuilder class in scripts/pipeline/shard_builder.py
[ ] ShardBuilder reads N_SHARDS env var, defaults to 4
[ ] ShardBuilder partitions sorted file list into N equal slices
[ ] ShardBuilder computes offset_i = i × (total_docs // N)
[ ] ShardBuilder uses ProcessPoolExecutor with max_workers=N
[ ] run_pipeline() as module-level function (picklable)
[ ] Output: shards/shard_{i}.bin (project root shards/ directory)
[ ] scripts/main_sharded.py entry point created
[ ] Makefile index-builder for PHASE=2 invokes main_sharded.py
```

### C++

```
[ ] boolean_engine.hpp uses #if PHASE == 1 / #else blocks (done)
[ ] boolean_engine.cpp wraps implementation in #if PHASE == 1 (done)
[ ] boolean_engine_p2.cpp created (done)
[ ] Makefile passes -DPHASE=$(PHASE) in CXXFLAGS (done)
[ ] Makefile excludes correct translation unit per phase (done)
[ ] BooleanEngine::init() accepts shard_dir, n_shards, use_priority_queue (done)
[ ] Loads all N shards from shards/ directory (done)
[ ] pairwise_merge() implemented (done)
[ ] priority_queue_merge() implemented (done)
[ ] do_merge() dispatches on use_priority_queue (done)
[ ] main.cpp parses --shards and --merge-strategy (done)
[ ] main.cpp forwards params to engine.init() (done)
[ ] --bench-init reports total init time across all N shards (done)
[ ] --bench mode works with N-shard fan-out (done)
[ ] All Phase 1 const correctness contracts preserved (done)
[ ] bench_init.py and bench_query.py updated to forward --shards and
    --merge-strategy to engine subprocess (pending)
```
