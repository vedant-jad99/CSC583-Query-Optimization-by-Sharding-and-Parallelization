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

Every significant design decision made during Phase 2 scoping is recorded here with full rationale. This section exists so that any team member can understand not just what was decided but why.

---

### Decision 1 — Document-based sharding over term-based sharding

**Options considered:**

**Term-based sharding:** The vocabulary is partitioned across shards. Each shard owns a subset of terms and stores posting lists for those terms covering the full corpus. A query only touches shards that contain its query terms.

**Document-based sharding:** The corpus is partitioned across shards. Each shard owns a subset of documents and builds a complete index over those documents. Every query fans out to all shards.

**Tradeoffs:**

| | Term-based | Document-based |
|---|---|---|
| Posting list size | Full corpus length | Fraction of corpus |
| Query fan-out | Targeted (only relevant shards) | All shards always |
| Shard balance | Uneven (high-freq terms dominate) | Even (by document count) |
| Build complexity | Higher (need full vocab first) | Lower (split docs, build independently) |
| NOT operation | Complex (universal set spans shards) | Clean (per-shard universal set) |
| Performance gain source | Vocabulary partitioning | Smaller posting lists |

**Decision: Document-based sharding.**

The performance story of this project is: smaller posting lists → faster Boolean set operations → lower query latency. Term-based sharding does not reduce posting list size — it only partitions the vocabulary. Document-based sharding directly reduces posting list length in proportion to the number of shards. This produces a clear, measurable performance gain that validates the benchmarking experiment.

Additionally, document-based sharding is simpler to build, produces evenly balanced shards, and has a cleaner universal doc ID set per shard for NOT operations.

---

### Decision 2 — Global doc ID consistency via presorting

**The problem:** In Phase 2, N independent pipeline processes each build their own index. If each process assigns doc IDs starting from 0, doc ID 5 in Shard 0 and doc ID 5 in Shard 1 refer to different documents. Merging results across shards produces a corrupt result set.

**Options considered:**

**Option A — Pre-hash filenames to IDs, save to JSON:**
A preprocessing script hashes each document filename to an integer ID and writes the mapping to a JSON file. Each pipeline reads the JSON and uses it to assign IDs.

Algorithmic complexity: O(1) per lookup. However, this analysis is incomplete. The full cost includes: writing the JSON (O(N) + disk I/O), reading it back (O(N) + disk I/O), and parsing it (O(N)). Total: O(N) with heavy I/O constants. Additionally, this introduces an extra file to manage and an external dependency on the preprocessing step completing before any pipeline can run.

**Option B — Presort corpus files, assign IDs by position with shard offset:**
The full corpus file list is sorted once alphabetically before any pipeline runs. Each shard receives a contiguous slice of the sorted list and a starting doc ID offset. Doc IDs are assigned as `offset + local_index`. Total cost: O(N log N) in-memory, zero disk I/O.

**Decision: Option B — presort with offset.**

In practice, O(N log N) in-memory sorting is dramatically faster than O(N) disk I/O for any realistic corpus size. Disk I/O constants are 100–1000x larger than in-memory computation constants. Sorting is simpler, requires no extra files, and produces globally unique doc IDs with zero coordination overhead between shard processes.

**Important:** The corpus file list must be sorted identically every time the pipeline runs. Sorting by full file path alphabetically is the standard. This is the single invariant the system relies on.

---

### Decision 3 — Sharding at build time in Python, not at query time in C++

**Options considered:**

**Build-time sharding (Python):** The Python pipeline partitions the corpus and writes N separate `.bin` files. The C++ engine simply loads N files — it has no knowledge of how they were created.

**Query-time sharding (C++):** A single `.bin` file is written (same as Phase 1). The C++ engine splits it into logical shards at load time.

**Decision: Build-time sharding in Python.**

Build-time sharding keeps the C++ engine read-only with respect to index structure. The engine's only responsibility is loading and querying — it never needs to understand sharding logic. This preserves the clean boundary established in Phase 1: Python writes, C++ reads. It also means the sharding logic is testable in isolation from the query engine. Query-time sharding would blur this boundary and add complexity to the C++ decompressor for no benefit.

---

### Decision 4 — Number of shards as environment variable, default 4

**Rationale:** A hardcoded shard count makes benchmarking inflexible. Making it configurable via environment variable allows the same codebase to be benchmarked with different shard counts (2, 4, 8) without recompilation. The default of 4 reflects the realistic core count on a development laptop and is a sensible starting point for benchmarking.

**Environment variable:** `N_SHARDS` (Python pipeline) and `N_SHARDS` (C++ engine, read at init time).

---

### Decision 5 — Parallel shard building via multiprocessing, not threading

**The problem:** Building N shards in parallel requires true parallelism — running N pipeline instances simultaneously on separate CPU cores. Python's `threading` module does not provide this for CPU-bound work due to the GIL (Global Interpreter Lock). The GIL is a mutex in CPython that prevents more than one thread from executing Python bytecode at the same time. For I/O-bound work (network, disk) threads are effective. For CPU-bound work (tokenization, stemming, encoding) they give concurrency but not parallelism — threads take turns on a single core.

**Decision: `multiprocessing` via `concurrent.futures.ProcessPoolExecutor`.**

`multiprocessing` spawns separate OS processes, each with its own Python interpreter and its own GIL. They run on separate CPU cores — true parallelism. `ProcessPoolExecutor` is the high-level wrapper that abstracts process lifecycle, error handling, and result collection. Each worker process runs a complete, independent `Pipeline` instance with no shared state. No locks, no synchronisation primitives needed.

---

### Decision 6 — New class: ShardBuilder

A new class `ShardBuilder` is introduced in Phase 2 as the top-level orchestrator for the sharded build process. It owns N `Pipeline` instances and manages the `ProcessPoolExecutor`. It is the only new Python class in Phase 2 — all other classes are inherited unchanged from Phase 1.

`ShardBuilder` is a build-time only construct. It has no equivalent in the C++ engine.

---

### Decision 7 — N QueryRunners in C++, one per shard

**Options considered:**

**Option A — Single QueryRunner, iterates over N shard indexes:**
One `QueryRunner` owns one `IRSubsystem`. The `IRSubsystem` is made aware of N indexes and iterates over them internally.

**Option B — N QueryRunners, one per shard, sequential execution:**
N `QueryRunner` instances, each owning its own `IRSubsystem` with its own shard's index. A coordinator runs them sequentially, collects N result vectors, merges.

**Decision: Option B — N QueryRunners.**

The decisive factor is Phase 3. In Phase 3, sequential execution across N `QueryRunner`s becomes concurrent execution across N threads. With Option B, that transition is exactly one change: replace sequential iteration with concurrent thread dispatch. `QueryRunner` and `IRSubsystem` themselves require zero modification. With Option A, `IRSubsystem` would need to be restructured to support concurrent access — a much larger and riskier change. Option B preserves the clean Phase 2 → Phase 3 delta, which is essential for credible benchmarking.

---

### Decision 8 — Preprocessor moved to BooleanEngine

**The problem:** In the original Phase 1 design, `Preprocessor` was owned by `QueryRunner`. In Phase 2 with N `QueryRunner` instances, this means the same raw query string is preprocessed N times, producing identical results each time. This is pure redundant computation and worsens with larger N.

**Decision:** `Preprocessor` is moved to `BooleanEngine`. `BooleanEngine` preprocesses the raw query exactly once and passes normalized terms to each `QueryRunner`. `QueryRunner` accepts normalized terms as input, not a raw query string.

This is also a better separation of concerns regardless of Phase 2: preprocessing is a concern of the engine as a whole, not of the individual query runner. This change is implemented in Phase 1 as an amendment.

---

### Decision 9 — No ShardManager class; merge lives on BooleanEngine

**Rationale:** A dedicated `ShardManager` class was considered to own the N `Decompressor` and N `QueryRunner` instances and coordinate query fan-out and merging. This was rejected as unnecessary indirection.

`BooleanEngine` is already the top-level coordinator. Adding `ShardManager` between `BooleanEngine` and `QueryRunner` adds a layer with no additional responsibility that `BooleanEngine` cannot own directly. Keeping merge logic on `BooleanEngine` keeps the design flat and readable.

---

### Decision 10 — Two merge strategies, switchable via environment flag

**Rationale:** Two merge algorithms are implemented and benchmarked:

**Pairwise merge:** Merge shard 0 and shard 1 results, then merge that with shard 2, then with shard 3. Simple to implement. O(M) per merge step where M is the size of the current result. Total: O(M × N).

**Priority queue k-way merge (heap merge):** Insert the first element of each shard's result vector into a min-heap. Pop minimum, advance that shard's pointer, insert next element. Repeat until all vectors are exhausted. O(M log N) total where M is total result count and N is number of shards.

For small N (4 shards), the difference is negligible in practice. However, implementing both and benchmarking them directly produces a meaningful data point for the project report and demonstrates algorithmic awareness.

**Environment variable:** `MERGE_STRATEGY` — values `PAIRWISE` or `PRIORITY_QUEUE`. Read at `BooleanEngine` init time.

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

### C++ — Changes

| Component | Status | Change |
|---|---|---|
| `Decompressor` | Unchanged | — |
| `Preprocessor` | **Amended in Phase 1** | Moved to BooleanEngine |
| `OpHandler` | Unchanged | — |
| `IRSubsystem` | Unchanged | — |
| `QueryRunner` | **Modified in Phase 2** | Accepts normalized terms, not raw query |
| `BooleanEngine` | **Modified in Phase 2** | Owns Preprocessor, N Decompressors, N QueryRunners, merge method |

---

## 4. Part 1 — Python Sharding Pipeline

### Class Hierarchy

```
pipeline.py (entry point)
├── presort_corpus()              ← Phase 1 amendment
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

---

#### `presort_corpus(corpus_dir)` — Phase 1 Amendment

- **Type:** Standalone function in `pipeline.py` entry point
- **Responsibility:** Produce a deterministic, globally consistent ordering of all corpus documents before any sharding or pipeline instantiation
- **Input:** Path to corpus directory
- **Output:** Sorted `list[str]` of full file paths
- **Sort key:** Full file path, alphabetical
- **Notes:** This must be called exactly once before `ShardBuilder` is instantiated. The sorted list is the authoritative document ordering for the entire system.

```python
def presort_corpus(corpus_dir: str) -> list[str]:
    files = [
        os.path.join(corpus_dir, f)
        for f in os.listdir(corpus_dir)
        if os.path.isfile(os.path.join(corpus_dir, f))
    ]
    return sorted(files)
```

---

#### `Pipeline` — Phase 1 Amendment

- **Change:** Constructor now accepts `file_slice: list[str]` and `doc_id_offset: int`
- **Behaviour:** Assigns doc IDs as `doc_id_offset + local_index` for each document in `file_slice`
- **Phase 1 compatibility:** Called with full file list and `offset=0` in single-pipeline mode — behaviour unchanged

---

#### `ShardBuilder` — Phase 2 New

- **Responsibility:** Top-level orchestrator for sharded index construction. Partitions the sorted corpus file list into N slices, computes doc ID offsets, and drives N `Pipeline` instances in parallel via `ProcessPoolExecutor`
- **Reads:** `N_SHARDS` environment variable (default: 4)
- **Owns:** `ProcessPoolExecutor`, N `Pipeline` worker functions
- **Output:** `shard_0.bin`, `shard_1.bin`, ..., `shard_{N-1}.bin`

**Execution flow:**
```
1. Read N_SHARDS from environment
2. Call presort_corpus() → sorted file list
3. Partition file list into N equal slices
4. Compute doc ID offset per shard: offset_i = i × (total_docs // N_SHARDS)
5. Spawn ProcessPoolExecutor with max_workers=N_SHARDS
6. Submit N pipeline tasks: run_pipeline(file_slice_i, offset_i, shard_id_i)
7. Wait for all futures to complete
8. Verify all N .bin files written successfully
```

**Worker function:**
```python
def run_pipeline(file_slice: list[str], offset: int, shard_id: int) -> None:
    pipeline = Pipeline(file_slice=file_slice, doc_id_offset=offset)
    pipeline.run(output_path=f"shard_{shard_id}.bin")
```

This function is a module-level function (not a method) because `ProcessPoolExecutor` requires picklable callables. Lambda functions and instance methods are not reliably picklable across processes.

**Why ProcessPoolExecutor over raw multiprocessing.Process:**
`ProcessPoolExecutor` abstracts process lifecycle management, exception propagation, and result collection. Raw `multiprocessing.Process` requires manual join, error handling, and IPC. `ProcessPoolExecutor` is cleaner, safer, and sufficient for this use case.

---

### Build Integration — Phase 2

```makefile
shards:
    N_SHARDS=4 python3 pipeline/pipeline.py \
      --corpus $(CORPUS_DIR) \
      --output-dir ./shards/

build: shards
    cmake --build .
```

---

## 5. Part 2 — C++ Query Engine

### Class Hierarchy

```
main.cpp
└── BooleanEngine
    ├── Preprocessor              ← moved from QueryRunner (Phase 1 amendment)
    ├── N × Decompressor          ← one per shard (Phase 2)
    ├── N × QueryRunner           ← one per shard (Phase 2)
    │         └── IRSubsystem
    │               └── OpHandler
    └── merge()                   ← new method (Phase 2)
          ├── pairwise_merge()
          └── priority_queue_merge()
```

---

### Unit Specifications

---

#### `Decompressor` — Unchanged

One instance per shard. Each loads its own `.bin` file via `mmap`. Behaviour identical to Phase 1. `BooleanEngine` instantiates N of them.

---

#### `Preprocessor` — Phase 1 Amendment (moved to BooleanEngine)

- Owned by `BooleanEngine`, not `QueryRunner`
- Called exactly once per query in `BooleanEngine::query()`
- Produces normalized terms passed to all N `QueryRunner` instances
- Internal behaviour unchanged: tokenize → case fold → punctuation remove → stop word filter → stem

---

#### `QueryRunner` — Modified in Phase 2

- **Change:** `query()` method now accepts `const vector<string>& normalized_terms` instead of `const string& raw_query`
- `Preprocessor` removed from ownership
- All other behaviour unchanged
- `IRSubsystem` instantiation and ownership unchanged

---

#### `IRSubsystem` — Unchanged

- Owns `OpHandler`
- Holds `const unordered_map<string, vector<uint32_t>>` and `const set<uint32_t>` for its shard
- Executes Boolean operations via `OpHandler`
- Returns `const vector<uint32_t>&`

---

#### `OpHandler` — Unchanged

- `AND` → linear merge intersection
- `OR` → linear merge union
- `NOT` → set difference against shard's universal doc ID set

---

#### `BooleanEngine` — Modified in Phase 2

- **Owns:** `Preprocessor`, N `Decompressor` instances, N `QueryRunner` instances
- **Reads:** `N_SHARDS` environment variable at init time
- **Reads:** `MERGE_STRATEGY` environment variable at init time (`PAIRWISE` or `PRIORITY_QUEUE`)

**`init(shard_dir)`:**
```cpp
for (int i = 0; i < n_shards; i++) {
    decompressors[i].load(shard_dir + "/shard_" + i + ".bin");
    queryRunners[i].init(
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
    shard_results.push_back(queryRunners[i].query(normalized));
}

return merge(shard_results);   // dispatches based on MERGE_STRATEGY
```

---

#### `merge()` — New Method on BooleanEngine

Dispatches to one of two implementations based on `MERGE_STRATEGY` environment variable read at init time.

---

**`pairwise_merge(shard_results)`:**

Merges result vectors sequentially, two at a time:
```
result = shard_results[0]
for i in 1..N:
    result = merge_two_sorted(result, shard_results[i])
return result
```
Complexity: O(M × N) where M is average result size, N is shard count.
Simple to implement and verify correct. Suitable for small N.

---

**`priority_queue_merge(shard_results)`:**

Classic k-way merge using a min-heap:
```
Insert (value, shard_index, element_index) for first element of each shard result
While heap not empty:
    Pop minimum (val, shard_i, elem_i)
    Append val to output
    If shard_i has more elements:
        Push next element from shard_i
Return output
```
Complexity: O(M log N) where M is total result count across all shards.
More efficient for large result sets or large N.

Both implementations return a sorted `vector<uint32_t>` of globally unique doc IDs. Since doc IDs are globally consistent across shards (guaranteed by the presort + offset scheme), no translation is needed before or after merging.

---

#### `main.cpp` — Phase 2

```cpp
BooleanEngine engine;
engine.init("./shards/");   // directory containing shard_0.bin ... shard_N.bin
// query loop
auto results = engine.query("information AND retrieval NOT theory");
```

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
 │  pipeline.py entry point                                                     │
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
 │  │  ├── Process 0: Pipeline(slice_0, offset=0)      → shard_0.bin          │ │
 │  │  ├── Process 1: Pipeline(slice_1, offset=25000)  → shard_1.bin          │ │
 │  │  ├── Process 2: Pipeline(slice_2, offset=50000)  → shard_2.bin          │ │
 │  │  └── Process 3: Pipeline(slice_3, offset=75000)  → shard_3.bin          │ │
 │  └─────────────────────────────────────────────────────────────────────────┘ │
 │                                                                              │
 │  Each Pipeline (per Phase 1 design):                                         │
 │  FileReader → Tokenizer → Normalizer → IndexBuilder → VBEncoder → BinWriter  │
 │                                                                              │
 │  Makefile: N_SHARDS=4 python3 pipeline.py --corpus ./docs --output-dir shards│
 └──────────────────────────────────────────┬───────────────────────────────────┘
                                            │
                          ┌─────────────────┼─────────────────┐
                          │                 │                 │
                          ▼                 ▼                 ▼
              ┌───────────────┐  ┌──────────────┐  ┌──────────────┐
              │  shard_0.bin  │  │  shard_1.bin │  │  shard_2.bin │  ...
              │  docs 0-24999 │  │ docs 25-49k  │  │ docs 50-74k  │
              │  [Phase 1 fmt]│  │ [Phase 1 fmt]│  │ [Phase 1 fmt]│
              └───────┬───────┘  └──────┬───────┘  └──────┬───────┘
                      │                 │                  │
  QUERY TIME          │    mmap ×N      │                  │
 ┌────────────────────┼─────────────────┼──────────────────┼──────────────────┐
 │  C++ QUERY ENGINE  │                 │                  │                  │
 │                    ▼                 ▼                  ▼                  │
 │  ┌──────────────────────────────────────────────────────────────────────┐  │
 │  │  main.cpp                                                            │  │
 │  │  BooleanEngine engine;  engine.init("./shards/");                    │  │
 │  │  engine.query("X AND Y NOT Z");                                      │  │
 │  └──────────────────────────────┬───────────────────────────────────────┘  │
 │                                 │                                          │
 │                                 ▼                                          │
 │  ┌──────────────────────────────────────────────────────────────────────┐  │
 │  │  BooleanEngine                                                       │  │
 │  │                                                                      │  │
 │  │  reads: N_SHARDS, MERGE_STRATEGY env vars                            │  │
 │  │                                                                      │  │
 │  │  ┌─────────────┐                                                     │  │
 │  │  │ Preprocessor│  raw query → normalized terms (once per query)      │  │
 │  │  └─────────────┘                                                     │  │
 │  │                                                                      │  │
 │  │  ┌────────────────┐  ┌────────────────┐  ┌────────────────┐          │  │
 │  │  │ Decompressor 0 │  │ Decompressor 1 │  │ Decompressor 2 │  ...     │  │
 │  │  │ mmap shard_0   │  │ mmap shard_1   │  │ mmap shard_2   │          │  │
 │  │  └───────┬────────┘  └───────┬────────┘  └───────┬────────┘          │  │
 │  │          │ std::move         │ std::move         │ std::move         │  │
 │  │          ▼                   ▼                   ▼                   │  │
 │  │  ┌───────────────┐  ┌───────────────┐  ┌───────────────┐             │  │
 │  │  │ QueryRunner 0 │  │ QueryRunner 1 │  │ QueryRunner 2 │  ...        │  │
 │  │  │               │  │               │  │               │             │  │
 │  │  │ IRSubsystem 0 │  │ IRSubsystem 1 │  │ IRSubsystem 2 │             │  │
 │  │  │  OpHandler    │  │  OpHandler    │  │  OpHandler    │             │  │
 │  │  └───────┬───────┘  └───────┬───────┘  └───────┬───────┘             │  │
 │  │          │                  │                  │                     │  │
 │  │      results_0          results_1          results_2   ...           │  │
 │  │          │                  │                  │                     │  │
 │  │          └──────────────────┴──────────────────┘                     │  │
 │  │                             │                                        │  │
 │  │                             ▼                                        │  │
 │  │  ┌──────────────────────────────────────────────────────────┐        │  │
 │  │  │  merge()  [dispatched by MERGE_STRATEGY env var]         │        │  │
 │  │  │                                                          │        │  │
 │  │  │  PAIRWISE:        O(M×N)  sequential two-way merge       │        │  │
 │  │  │  PRIORITY_QUEUE:  O(M logN)  k-way heap merge            │        │  │
 │  │  └──────────────────────────────────────────────────────────┘        │  │
 │  └──────────────────────────────────────────────────────────────────────┘  │
 │                                 │                                          │
 │                                 ▼                                          │
 │                    const vector<uint32_t>&                                 │
 │                    globally unique result doc IDs                          │
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
                    →  shard_0.bin ... shard_N.bin

shard_i.bin         →  Decompressor_i (mmap)
                    →  unordered_map + set<uint32_t>  (shard i's index)
                    →  std::move → IRSubsystem_i

raw query           →  Preprocessor (once, in BooleanEngine)
                    →  normalized terms
                    →  QueryRunner_0 ... QueryRunner_N (sequential)
                    →  results_0 ... results_N
                    →  merge() → final globally unique doc IDs
```

---

## 8. Key Design Decisions Table

| Decision | Choice | Rationale |
|---|---|---|
| Sharding strategy | Document-based | Smaller posting lists → faster set ops; clean benchmark variable |
| Doc ID consistency | Presort + offset | O(N log N) in-memory beats O(N) disk I/O; no extra files |
| Shard build location | Python build time | Preserves Python writes / C++ reads boundary |
| Shard count | Configurable via N_SHARDS env var, default 4 | Flexible benchmarking across different shard counts |
| Python parallelism | multiprocessing via ProcessPoolExecutor | True CPU parallelism; threads cannot due to GIL |
| C++ query structure | N QueryRunners sequential | Phase 3 transition = one change (sequential → concurrent) |
| Preprocessor location | BooleanEngine | Preprocess once per query; better separation of concerns |
| ShardManager | Not implemented | BooleanEngine is already the coordinator; no extra layer needed |
| Merge strategy | Both pairwise and k-way, switchable via env var | Benchmarkable experiment; demonstrates algorithmic tradeoff |

---

## 9. Benchmarking Additions for Phase 2

The Phase 1 benchmarking framework is reused entirely. The following additions are made:

### New Benchmark Dimension — Merge Strategy

`bench_query.py` is extended to accept a `--merge-strategy` flag (`PAIRWISE` or `PRIORITY_QUEUE`). The C++ engine is launched with the corresponding `MERGE_STRATEGY` env var. Results are written to separate JSON files per strategy.

### New Metric — Per-shard Query Time

The C++ engine can optionally report per-shard query time when run with `--bench-verbose`. This allows the benchmark to show how much time is spent querying each shard versus merging.

### New Result Directory Structure

```
results/
├── phase1/
├── phase2/
│   ├── pairwise/
│   └── priority_queue/
└── phase3/
```

### Cross-Phase Comparison

`report.py --compare 1 2` now also shows:
- Latency delta: Phase 1 vs Phase 2 (pairwise) vs Phase 2 (priority queue)
- Throughput delta across phases and merge strategies

---

## 10. Implementer Checklist

### Python

```
[ ] presort_corpus() function added to pipeline.py entry point (Phase 1 amendment)
[ ] Pipeline accepts file_slice and doc_id_offset parameters (Phase 1 amendment)
[ ] Pipeline assigns doc IDs as offset + local_index
[ ] ShardBuilder class created
[ ] ShardBuilder reads N_SHARDS from environment, defaults to 4
[ ] ShardBuilder partitions sorted file list into N equal slices
[ ] ShardBuilder computes correct offset per shard
[ ] ShardBuilder uses ProcessPoolExecutor with max_workers=N_SHARDS
[ ] run_pipeline() implemented as module-level function (picklable)
[ ] Each shard writes to shard_{i}.bin
[ ] Makefile target updated for sharded build
```

### C++

```
[ ] Preprocessor removed from QueryRunner (Phase 1 amendment)
[ ] Preprocessor instantiated in BooleanEngine constructor (Phase 1 amendment)
[ ] BooleanEngine.query() preprocesses raw query before passing to QueryRunners
[ ] QueryRunner.query() accepts const vector<string>& normalized_terms
[ ] BooleanEngine reads N_SHARDS env var at init
[ ] BooleanEngine reads MERGE_STRATEGY env var at init
[ ] BooleanEngine instantiates N Decompressors and N QueryRunners
[ ] BooleanEngine.init() loads all N shard .bin files
[ ] pairwise_merge() implemented
[ ] priority_queue_merge() implemented
[ ] merge() dispatches correctly based on MERGE_STRATEGY
[ ] --bench-init flag reports total init time across all N shards
[ ] --interactive mode works correctly with N-shard fan-out
[ ] All Phase 1 const correctness contracts preserved
```
