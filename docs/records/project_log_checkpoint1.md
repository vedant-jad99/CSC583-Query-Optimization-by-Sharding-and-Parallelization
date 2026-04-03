# Query Engine Project — Complete Log & Checkpoint

**Project:** Query Optimization via Parallelization and Sharded Indexing  
**Document Type:** Design Log & Decision Record  
**Checkpoint:** 1 — Pre-Implementation  
**Date:** April 3, 2026  
**Author:** Vedant Keshav Jadhav, MS CS, University of Arizona

---

## Purpose

This document is a complete chronological record of every design discussion, decision, agreement, disagreement, and rationale from the start of the project through Checkpoint 1. It serves as a reference for implementation, a history check for future design decisions, and an onboarding document for any team member joining mid-project.

It should be updated periodically at each major checkpoint.

---

## Table of Contents

1. [Project Genesis](#1-project-genesis)
2. [Project Structure — Two Tracks](#2-project-structure--two-tracks)
3. [Phase 1 — Python Pipeline Design](#3-phase-1--python-pipeline-design)
4. [Phase 1 — Bin File Format](#4-phase-1--bin-file-format)
5. [Phase 1 — C++ Engine Design](#5-phase-1--c-engine-design)
6. [Phase 1 — Design Review](#6-phase-1--design-review)
7. [Benchmarking and Profiling Design](#7-benchmarking-and-profiling-design)
8. [Phase 1 Amendments](#8-phase-1-amendments)
9. [Phase 2 — Sharding Design](#9-phase-2--sharding-design)
10. [Phase 2 — C++ Engine Design](#10-phase-2--c-engine-design)
11. [Phase 3 — Preliminary Design](#11-phase-3--preliminary-design)
12. [Project Plan PDF Review](#12-project-plan-pdf-review)
13. [Open Items and Stretch Goals](#13-open-items-and-stretch-goals)
14. [Complete Decision Registry](#14-complete-decision-registry)
15. [Document Registry](#15-document-registry)
16. [Signatures](#16-signatures)

---

## 1. Project Genesis

### Background
Vedant Keshav Jadhav is an MS CS student at the University of Arizona (GPA 3.8), graduating May 2026. He has a background as a System Software Engineer at NVIDIA Bangalore (2022–2024) and interned at NVIDIA Santa Clara (2025). He is enrolled in CSC583 (Text Retrieval and Web Search, taught by Prof. Mihai Surdeanu) and holds a Qualcomm offer for a camera team role.

### Original CSC583 Project
The initial CSC583 project was an FM-index implementation based on:
- Ferragina & Manzini, JACM 2005
- Navarro et al., TOIS 2000

This was cancelled due to time constraints.

### Replacement Project
The FM-index project was replaced with a query optimization system focused on parallelization and sharded indexing. This became the subject of all subsequent design work.

---

## 2. Project Structure — Two Tracks

### Decision: Two Parallel Tracks
**Agreed:** The project runs on two parallel tracks:

**Track 1 — Solo Personal Build:**
Vedant owns everything end-to-end. No shortcuts, no LLM-generated code. Full Python indexing pipeline + C++ query engine with parallelization and sharded indexing across three benchmarked phases. This is the rigorous, systems-correct implementation.

**Track 2 — CSC583 Course Project:**
Same concept, split across the group, with heavy LLM assistance. Scoped to the semester timeline and grading rubric.

**Rationale:** The solo build gives Vedant deep ground-truth knowledge of how the system should work, making him a strong technical anchor for the group project.

**Working style:** Vedant serves as the primary decision-maker. Claude serves as a sounding board, reviewer, and design collaborator.

---

## 3. Phase 1 — Python Pipeline Design

### High-Level Vision (Agreed)
An end-to-end Python pipeline for data processing and index creation:
- Read → Parse → Tokenize → Normalize → Build inverted index → Serialize → Compress → Write to `.bin` file
- Works for small and large datasets (generalized design)
- Runs as a build-time step before C++ query engine executes

### Class Structure (Agreed)
Three main classes:
- **`IndexCreator`** — owns all data handling: reading, parsing, tokenizing, normalizing, building the in-memory inverted index
- **`MakeBinFile`** — owns serialization: VByte encoding, writing binary format
- **`Pipeline`** — top-level orchestrator, owns `IndexCreator` and `MakeBinFile`

### Subclass Structure (Agreed)
Subclasses are decoupled for clean implementation, benchmarking, and debugging:

**Under `IndexCreator`:**
- `FileReader` — reads raw documents, assigns doc IDs
- `Tokenizer` — splits text into tokens
- `Normalizer` — orchestrates normalization pipeline
  - `CaseFolder`
  - `PunctuationRemover`
  - `StopWordFilter`
  - `Stemmer` (Porter/Snowball — must match C++ Preprocessor exactly)
- `IndexBuilder` — builds `dict[str, list[int]]`, deduplicates, sorts posting lists

**Under `MakeBinFile`:**
- `VBEncoder` — delta encode then VByte encode posting lists
- `BinWriter` — writes binary file in agreed format

### Normalization Pipeline Order (Agreed)
CaseFold → PunctuationRemove → StopWordFilter → Stem

### Stop Words (Agreed)
Stop word removal included. Rationale: posting lists for high-frequency words like "the" or "is" would be enormous without it. Filtered at indexing time.

### Static Index (Agreed)
Index is write-once, immutable after construction. No dynamic updates. Simplifies design and removes concurrent write concerns.

### Stemmer Contract (Agreed)
The stemmer used in Python (`Normalizer` → `Stemmer`) must be identical in algorithm to the stemmer used in C++ (`Preprocessor`). This ensures query terms match indexed terms. Both use Porter stemmer.

### Build Integration (Agreed)
Pipeline runs as a Makefile pre-build step:
```makefile
index.bin:
    python3 pipeline/pipeline.py --corpus $(CORPUS_DIR) --out index.bin
build: index.bin
    cmake --build .
```
CMake `add_custom_command` was considered but rejected as less portable. Makefile preferred.

---

## 4. Phase 1 — Bin File Format

### Format (Agreed)
```
[8  bytes]  Magic string + version        e.g. "QEIDX\x00\x01\x00"
[4  bytes]  Number of terms               uint32 little-endian
── per term (repeats) ─────────────────────────────────────────
[2  bytes]  Term length (M)               uint16 little-endian
[4  bytes]  Doc ID count (N)              uint32 little-endian
[M  bytes]  Term string                   UTF-8, no null terminator
[N  bytes]  VByte-encoded delta doc IDs
───────────────────────────────────────────────────────────────
[4  bytes]  CRC32 checksum                uint32 little-endian (optional)
```

### Endianness (Agreed)
Little-endian throughout. Python `struct` uses `<` prefix. C++ reads on x86. Pinned explicitly to avoid cross-language mismatch.

### VByte Encoding Scheme (Agreed)
```
For each value:
  while value > 127:
    emit (value & 0x7F)      # lower 7 bits, continuation bit = 0
    value >>= 7
  emit (value | 0x80)        # final byte, continuation bit = 1
```

### Delta Encoding (Agreed)
Posting lists must be sorted. Store differences between consecutive doc IDs (deltas), not absolute values. First doc ID stored as-is. Small deltas → fewer bytes per VByte code. This is a stated contract, not an implementation afterthought.

### Checksum (Agreed)
Optional. CRC32. Deferred for Phase 1, may be added later.

### Universal Doc ID Set for NOT Operations (Agreed)
**Considered:** Including universal set in bin file.
**Rejected:** More I/O, larger bin file.
**Decided:** Build universal set on the fly in C++ Decompressor as a union of all posting lists during parse. A document absent from all posting lists is one with no indexable tokens — negligible edge case in practice.

---

## 5. Phase 1 — C++ Engine Design

### Class Structure (Agreed)

```
main.cpp
└── BooleanEngine
    ├── Preprocessor              (owned by BooleanEngine — Phase 1 amendment)
    ├── Decompressor              (decompressor.hpp / decompressor.cpp)
    └── QueryRunner
        └── IRSubsystem
              └── OpHandler
```

### BooleanEngine (Agreed)
- Top-level orchestrator
- Owns `Preprocessor`, `Decompressor`, `QueryRunner`
- Constructor instantiates `QueryRunner`
- `init(path)` — separate from constructor, loads index
- `init()` calls `decompressor.load(path)`, then `queryRunner.init(std::move(index), std::move(docIDs))`

### Decompressor (Agreed)
- Separate translation unit: `decompressor.hpp` / `decompressor.cpp`
- `load(path)` — mmaps bin file, walks pointer, VByte decodes, delta expands, builds index and universal doc ID set, munmaps
- `getIndex()` → `unordered_map<string, vector<uint32_t>>&&` (rvalue ref for move)
- `getDocIDs()` → `set<uint32_t>&&` (rvalue ref for move)
- After move, Decompressor internals are empty — intentional

### mmap Decision (Agreed)
Traditional file I/O rejected in favour of `mmap`. Rationale: no kernel→userspace copy, no explicit `read()` syscalls, OS handles page prefetch for sequential access. For a static, read-once, sequential parse — ideal use case. POSIX only (Linux/macOS). Windows portability not a concern for this project.

### Preprocessor (Agreed — amended from original)
- Originally owned by `QueryRunner`
- **Amended:** Moved to `BooleanEngine`
- Preprocesses raw query exactly once before passing normalized terms to `QueryRunner`
- Operations: tokenize → case fold → punctuation remove → stop word filter → stem
- Must use same stemmer algorithm as Python side
- Does **not** reorder tokens — preserves query structure for postfix parsing

### QueryRunner (Agreed)
- Constructor instantiates `Preprocessor` — **corrected:** `Preprocessor` is now in `BooleanEngine`, not `QueryRunner`
- Constructor does **not** instantiate `IRSubsystem` — separate `init()` handles that
- `init(index, docIDs)` — instantiates `IRSubsystem` with moved-in index and doc IDs
- Accepts normalized terms from `BooleanEngine`, not raw query string

### IRSubsystem (Agreed)
- Owns `OpHandler`
- Instantiated in `QueryRunner::init()` with `const unordered_map<string, vector<uint32_t>>` and `const set<uint32_t>`
- Handles postfix query parsing and evaluation internally
- Returns `const vector<uint32_t>&`

### Query Parsing — Postfix (Agreed — late addition)
- Boolean queries are parsed into postfix form (shunting-yard algorithm) inside `QueryRunner` or `IRSubsystem`
- `Preprocessor` normalizes tokens only — does not reorder or restructure query
- `OpHandler` executes the postfix stack:
  - Operands are posting lists
  - AND/OR pop two lists, apply set operation, push result
  - NOT is unary — pops one list, diffs against universal set

### OpHandler (Agreed)
- AND → linear merge intersection O(m+n) — posting lists are sorted
- OR → linear merge union O(m+n)
- NOT → set difference against universal doc ID set
- All inputs `const vector<uint32_t>&`
- Returns owned `vector<uint32_t>`

### std::move Handoff (Agreed)
```cpp
queryRunner.init(
    std::move(decompressor.getIndex()),
    std::move(decompressor.getDocIDs())
);
```
Single transfer, zero copies. After move, Decompressor internals are empty.

### Const Correctness Contract (Agreed)
| Object | Type |
|---|---|
| Inverted index in IRSubsystem | `const unordered_map<string, vector<uint32_t>>` |
| Universal doc ID set | `const set<uint32_t>` |
| Posting list lookups | `const vector<uint32_t>&` |
| OpHandler inputs | `const vector<uint32_t>&` |
| Query results | `const vector<uint32_t>&` |

### Ownership Model (Agreed — reconfirmed against PDF)
- `BooleanEngine` owns `QueryRunner`
- `QueryRunner` owns `IRSubsystem`
- `QueryRunner` constructor does NOT instantiate `IRSubsystem`
- Separate `init()` instantiates `IRSubsystem`
- Index and doc ID set passed to `IRSubsystem` at `init()` via `std::move`
- Implementation detail — not required in architecture doc

---

## 6. Phase 1 — Design Review

### Review Points Raised (by Claude, accepted by Vedant)

**Delta encoding must be explicit:**
VByte alone is insufficient. Doc IDs must be sorted and delta-encoded before VByte encoding. This is a contract, not an implementation detail. Accepted and incorporated.

**Endianness must be pinned:**
Multi-byte fields written by Python, read by C++. Must agree on endianness explicitly. Little-endian chosen. Accepted.

**Stop word removal:**
Not in original pipeline description. Raised as a gap. Accepted — added to Normalizer.

**CMake integration caution:**
Running Python as CMake pre-build step is messy — dependency tracking, virtual env, Python path issues. Makefile with explicit targets recommended. Accepted.

**In-memory index structure must be explicit:**
`std::unordered_map<string, vector<uint32_t>>`. Agreed and stated explicitly.

---

## 7. Benchmarking and Profiling Design

### Philosophy (Agreed)
External benchmark scripts, completely decoupled from engine code. Same scripts run against Phase 1, 2, and 3 without modification. Portability was the deciding factor over built-in instrumentation.

### Metrics (Agreed)
- **Indexing time** — Python pipeline wall clock
- **Init/load time** — C++ engine startup (mmap + decompress + index build)
- **Query latency** — per query, excluding init
- **Query throughput** — queries per second over batch
- **Peak memory (Python)** — `tracemalloc`
- **Peak memory (C++)** — `/usr/bin/time -v`
- **Index size on disk** — MB

### Statistical Reporting (Agreed)
Never measure a single run. Always report: mean, median, p95, p99, min, max. Warmup: 10 queries discarded before measurement. Repetitions: 50 per query.

### Corpus Scale (Agreed)
Two sizes: small (~5,000 docs) for sanity checking, large (100,000+ docs, MS MARCO) for meaningful results. WikiText-2 as small control corpus.

### Query Workload (Agreed)
Fixed, repeatable query files:
- `short.txt` — single term
- `medium.txt` — two terms, one operator
- `complex.txt` — multi-operator

100–500 queries per category. Same files used across all three phases.

### C++ Engine Interface (Agreed)
stdin/stdout query loop (`--interactive` mode). Engine prints `READY` when init complete, reads queries from stdin, prints results to stdout. Separate `--bench-init` flag for init-only timing. Rationale: low overhead, realistic, easy to script, no networking complexity.

### Results Format (Agreed)
JSON files per run, timestamped, written to `results/phase1/`, `results/phase2/`, `results/phase3/`. `report.py` aggregates across phases.

### Tooling (Agreed)
Python: `time.perf_counter()`, `tracemalloc`, `cProfile`, `numpy.percentile()`
C++: `std::chrono::high_resolution_clock`, `/usr/bin/time -v`, `valgrind --tool=callgrind`, `perf stat`
Compiler: always `-O2 -std=c++17` for benchmarking. Never debug build.

---

## 8. Phase 1 Amendments

### Amendment 1 — Corpus Presorting and Doc ID Offset Logic

**Why needed:** Phase 2 runs N independent pipeline processes. Without a globally consistent doc ID scheme, IDs from different shards collide and merge results are corrupt.

**Decision — Presorting over JSON hashing:**
A pre-hash approach (filename → integer ID saved to JSON) was proposed by Vedant. Analysed and rejected on performance grounds:
- JSON approach: O(1) lookup but requires O(N) write + O(N) read + O(N) parse with disk I/O
- Sort approach: O(N log N) entirely in-memory, zero disk I/O
- In practice, O(N log N) in-memory is dramatically faster than O(N) disk I/O for realistic corpus sizes
- Disk I/O constants are 100–1000x larger than in-memory computation constants
- Sort also requires no extra files, no external dependencies

**Changes:**
- `presort_corpus()` function added to `pipeline.py` entry point — sorts all corpus files by full path alphabetically
- `Pipeline` class extended to accept `file_slice: list[str]` and `doc_id_offset: int`
- Doc IDs assigned as `offset + local_index`
- Phase 1 single-pipeline call: `file_slice = all_files`, `offset = 0` — behaviour unchanged

### Amendment 2 — Preprocessor Moved to BooleanEngine

**Why needed:** In Phase 2, `BooleanEngine` owns N `QueryRunner` instances. If `Preprocessor` remains in `QueryRunner`, the same query is preprocessed N times producing identical results — pure redundant computation.

**Change:**
- `Preprocessor` removed from `QueryRunner`
- `Preprocessor` instantiated in `BooleanEngine` constructor
- `BooleanEngine::query()` preprocesses raw query once, passes normalized terms to each `QueryRunner`
- `QueryRunner::query()` accepts `const vector<string>& normalized_terms`

**Additional rationale:** Better separation of concerns regardless of Phase 2. Preprocessing is an engine-level concern, not a runner-level concern.

---

## 9. Phase 2 — Sharding Design

### Sharding Strategy Decision (Agreed)

**Considered:** Term-based sharding vs document-based sharding.

**Term-based sharding:** Vocabulary partitioned across shards. Each shard owns a subset of terms, covering all documents. Targeted fan-out — query only touches relevant shards.
- Problem: posting lists remain full-corpus length. No reduction in set operation cost.
- Problem: uneven shard sizes due to term frequency distribution.
- Problem: harder to build — full vocabulary needed before partitioning.
- Problem: NOT operation complex — universal set spans all shards.

**Document-based sharding:** Corpus partitioned across shards. Each shard owns a subset of documents with a complete index over those documents. Every query fans out to all shards.
- Benefit: posting lists are a fraction of full-corpus size → faster Boolean set operations.
- Benefit: evenly balanced shards by document count.
- Benefit: simpler to build — split docs, build independently.
- Benefit: universal doc ID set per shard is naturally bounded.

**Decision: Document-based sharding.**
The performance story is: smaller posting lists → faster Boolean set operations → lower query latency. Term-based sharding does not reduce posting list size. Document-based sharding does, directly and measurably.

### Shard Count (Agreed)
Configurable via `N_SHARDS` environment variable. Default: 4. Rationale: reflects realistic core count on development laptop; configurable for benchmarking flexibility.

### Build-Time Sharding (Agreed)
Sharding happens at index build time in Python. C++ engine reads N `.bin` files, has no knowledge of sharding strategy. Preserves the Python writes / C++ reads boundary from Phase 1.

### Python Parallelism — ProcessPoolExecutor (Agreed)
Threading rejected: CPU-bound work; Python GIL prevents true parallelism for threads.
`multiprocessing` via `concurrent.futures.ProcessPoolExecutor` chosen. Separate OS processes, each with own Python interpreter and GIL. True parallelism on separate CPU cores. No shared state, no locks needed between shard processes.

### ShardBuilder Class (Agreed)
New class in Phase 2. Top-level orchestrator for sharded build. Owns N `Pipeline` instances via `ProcessPoolExecutor`. Reads `N_SHARDS` from environment. Writes `shard_0.bin` ... `shard_{N-1}.bin`. Build-time only — no C++ equivalent.

**Naming considered:** ShardCoordinator (rejected), ShardDispatcher (rejected), ParallelIndexer (rejected), IndexShardWriter (rejected). **ShardBuilder accepted.**

### Worker Function Must Be Module-Level (Agreed)
`run_pipeline()` must be a module-level function, not a lambda or instance method. `ProcessPoolExecutor` requires picklable callables. Lambdas and instance methods are not reliably picklable across processes.

---

## 10. Phase 2 — C++ Engine Design

### N QueryRunners (Agreed)

**Considered:**
- Option A: Single `QueryRunner`, `IRSubsystem` iterates over N indexes internally
- Option B: N `QueryRunner` instances, sequential execution, results merged after

**Decision: Option B.**
Decisive factor: Phase 3 transition. With Option B, Phase 3 = replace sequential iteration with concurrent `std::async`. `QueryRunner` and `IRSubsystem` unchanged. With Option A, `IRSubsystem` would need restructuring for concurrent access — much larger change. Option B preserves the clean Phase 2 → Phase 3 delta for valid benchmarking.

### No ShardManager Class (Agreed)
A dedicated `ShardManager` class was considered. Rejected as unnecessary indirection. `BooleanEngine` is already the top-level coordinator. No extra layer needed.

### BooleanEngine in Phase 2 (Agreed)
- Owns `Preprocessor`, N `Decompressor` instances, N `QueryRunner` instances
- Reads `N_SHARDS` and `MERGE_STRATEGY` from environment at init
- `init(shard_dir)` — loads all N shard `.bin` files
- `query()` — preprocesses once, fans out to N `QueryRunner`s sequentially, merges

### Merge Strategy (Agreed)
Two implementations, switchable via `MERGE_STRATEGY` environment variable:

**PAIRWISE:** Merge results two at a time sequentially. O(M × N). Simple, correct, easy to verify.

**PRIORITY_QUEUE:** K-way merge via min-heap. O(M log N). More efficient for large result sets or large N.

**Rationale for both:** Implementing and benchmarking both produces a meaningful data point. Demonstrates algorithmic awareness. The benchmark delta between strategies is a project result in itself.

**Note:** For N=4 the practical difference is negligible. The experiment value is in demonstrating the methodology.

---

## 11. Phase 3 — Preliminary Design

**Status:** Intentionally incomplete. To be solidified after Phase 1 and Phase 2 benchmarking and profiling.

### Confirmed Decisions

**True parallelism via C++ threads:**
C++ threads are native OS threads — not subject to GIL. Four threads → four cores. True parallelism without multiprocessing workaround.

**N workers fixed at 4, configurable via N_WORKERS env var.**

**No shared mutable state between threads:**
Each `QueryRunner` owns its own `IRSubsystem`, `OpHandler`, const index, const universal set. Zero synchronisation primitives needed during query execution. Coordination point is only result collection after all threads complete.

**Result ownership via `std::future`:**
Each thread returns owned `vector<uint32_t>` — copy of `const` result from `QueryRunner`. Collected via `std::future`. No pre-allocated shared containers. No stale state between queries.

**Merge unchanged from Phase 2:**
Both PAIRWISE and PRIORITY_QUEUE strategies. Runs on main thread after all threads complete. No incremental merge for now.

**Sequential queries, parallel execution within each query:**
`BooleanEngine::query()` is synchronous. Blocks until all threads complete and merge returns. Next query cannot begin until current one fully resolves.

**Baseline implementation: `std::async`:**
```cpp
vector<future<vector<uint32_t>>> futures;
for (int i = 0; i < n_shards; i++) {
    futures.push_back(std::async(std::launch::async, [&, i]() {
        return vector<uint32_t>(queryRunners[i].query(normalized));
    }));
}
vector<vector<uint32_t>> results;
for (auto& f : futures) results.push_back(f.get());
return merge(results);
```

**`std::async` vs `std::thread` + join:**
`std::async` chosen over raw threads: future owns result cleanly (no shared container), exceptions captured and re-thrown on `.get()`, thread lifecycle automatic. Raw threads require manual join, shared result containers, manual error handling.

### Open TODOs (Deferred to Post-Phase 2 Profiling)

**TODO 1 — Thread lifecycle: `std::async` vs persistent thread pool:**
`std::async` may spawn a new thread per query (implementation-defined). Thread creation overhead is 10–50µs on Linux. Whether this is significant depends on per-shard query latency, which Phase 2 benchmarks will reveal.
- If median shard query time > 1ms → `std::async` fine
- If median shard query time < 500µs → persistent thread pool warranted

**TODO 2 — Worker count independence from shard count:**
Currently N_WORKERS = N_SHARDS. If N_SHARDS increases beyond physical core count, more threads than cores causes context switching overhead. Experiment with N_WORKERS < N_SHARDS post-Phase 2.

**TODO 3 — Incremental merge:**
Current: wait for all threads, then merge. Alternative: merge as each thread completes, overlapping merge with remaining execution. Worth evaluating if merge time > 10% of total query time.

**TODO 4 — Exception handling across threads:**
`std::async` captures exceptions via future. Explicit strategy (abort, partial results, retry) deferred. Low priority for Phase 3.

---

## 12. Project Plan PDF Review

### Document Reviewed
"Query Optimization via Parallelization and Sharded Indexing" — formal project plan submitted to Prof. Mihai Surdeanu, CSC583, Spring 2026.

### Alignment Assessment

**Fully aligned with our design:**
- Three-phase structure
- Python corpus processing + C++ query engine
- Binary index serialization
- Boolean retrieval (AND/OR/NOT)
- Document-based sharding
- Benchmarking on WikiText-2 and MS MARCO
- `std::async` for Phase 3

**In the PDF but not in our MVP (stretch goals):**
- Three shard lookup policies (broadcast, exact catalog, bloom filter) — our MVP implements broadcast only
- Per-term posting list parallelism in Phase 3 — our MVP parallelises at per-shard level
- Concurrent min-heap merge for OR queries
- Amdahl's law speedup curve (thread count 1–16)
- Bloom filter false positive rate tuning

**In our design but not explicit in PDF:**
- VByte + delta encoding detail
- mmap for decompressor
- Const correctness contract
- Detailed class hierarchy and ownership model
- Benchmarking framework design (external scripts, JSON results, report.py)
- Postfix query parsing (shunting-yard) — mentioned in PDF, confirmed for our design

### Postfix Query Parsing (Agreed — confirmed from PDF)
Boolean queries parsed into postfix form using shunting-yard algorithm. Lives in `QueryRunner` or `IRSubsystem`. `Preprocessor` normalizes tokens only — does not reorder. `OpHandler` executes postfix stack.

### Ownership Model Reconfirmation (Agreed)
`BooleanEngine` owns `QueryRunner`. `QueryRunner` owns `IRSubsystem`. `QueryRunner` constructor does not instantiate `IRSubsystem`. Separate `init()` does. Index and doc IDs passed via `std::move`. Our existing architecture stands — PDF's `unique_ptr` model not adopted.

### Professor's Question — Resolved
Prof. Surdeanu asked: "How will you show that your improved implementation is better?"

Response sent: Phase-controlled benchmarking. One variable per phase. Phase 1 is ground truth. Phases 2 and 3 reported as deltas. Same query set, corpus, hardware across all phases. Key metrics: latency (mean and p99), throughput, build time. MVP implements 100% of functional requirements; extended features (bloom filter, concurrent merge, Amdahl analysis) are stretch goals.

### MVP Scope Definition (Agreed)
- **In MVP (100% functional requirements):** Three-phase pipeline, Boolean IR engine, document sharding, parallel index build, parallel query execution, benchmarking framework, correctness verification
- **Stretch goals (time permitting):** Bloom filter shard routing, exact catalog routing, concurrent min-heap merge, Amdahl curve, per-term parallelism, lock-free merge, distributed gRPC shards, TF-IDF/BM25 scoring

---

## 13. Open Items and Stretch Goals

### Open Design Items (Must resolve before implementation)
None. All blocking design decisions are resolved as of Checkpoint 1.

### Open Implementation Items (Deferred to post-Phase 2 profiling)
- TODO 1: Thread lifecycle model for Phase 3
- TODO 2: N_WORKERS vs N_SHARDS independence
- TODO 3: Incremental merge evaluation
- TODO 4: Exception handling across threads

### Stretch Goals (Time permitting, after MVP complete)
- Bloom filter shard router
- Exact catalog shard router (term → shard_id map)
- Concurrent min-heap merge for OR queries
- Per-term posting list parallelism
- Amdahl's law speedup curve (thread count 1–16)
- Lock-free posting list merge using atomics
- Distributed query via gRPC (shards as separate processes)
- TF-IDF or BM25 scoring layer on Phase 1

---

## 14. Complete Decision Registry

| # | Decision | Options Considered | Chosen | Rationale |
|---|---|---|---|---|
| 1 | Project tracks | One vs two | Two (solo + course) | Solo build = ground truth; course build = group scope |
| 2 | Pipeline language | Python vs C++ | Python for indexing, C++ for engine | Python: rapid development, rich text libs. C++ : performance |
| 3 | Retrieval model | Ranked, Boolean, positional | Boolean only (Phase 1) | Cleanest baseline for benchmarking sharding/parallelism |
| 4 | Compression | VByte only vs VByte + delta | VByte + delta | Delta encoding reduces values; fewer bytes per VByte code |
| 5 | Endianness | Big vs little | Little-endian | x86 native; explicit contract between Python and C++ |
| 6 | Checksum | Include vs defer | Optional/deferred | Not strictly needed for Phase 1 |
| 7 | Universal set (NOT) | In bin file vs on-the-fly | On-the-fly in Decompressor | No I/O overhead; missing-doc edge case negligible |
| 8 | Stop words | Include vs skip | Include | Prevents enormous posting lists for high-freq terms |
| 9 | File I/O in C++ | Traditional read() vs mmap | mmap | No kernel→userspace copy; OS prefetch; lower init latency |
| 10 | Build integration | CMake vs Makefile | Makefile | Simpler, more portable, cleaner dependency tracking |
| 11 | Preprocessor location | QueryRunner vs BooleanEngine | BooleanEngine | Preprocess once per query; better separation of concerns |
| 12 | Shard strategy | Term-based vs document-based | Document-based | Smaller posting lists → faster set ops; clean benchmark |
| 13 | Doc ID consistency | JSON hash map vs presort+offset | Presort+offset | O(N log N) in-memory beats O(N) disk I/O; no extra files |
| 14 | Shard count | Fixed vs configurable | Configurable (N_SHARDS env), default 4 | Flexible benchmarking across shard counts |
| 15 | Python parallelism | threading vs multiprocessing | ProcessPoolExecutor | GIL prevents thread parallelism for CPU-bound work |
| 16 | C++ query structure | Single QueryRunner vs N QueryRunners | N QueryRunners | Phase 3 transition = one change; clean benchmark delta |
| 17 | ShardManager class | Include vs exclude | Exclude | BooleanEngine is already coordinator; no extra layer |
| 18 | Merge strategy | Pairwise vs priority queue | Both, switchable via env | Benchmarkable experiment; demonstrates algorithmic tradeoff |
| 19 | Phase 3 baseline | std::async vs thread pool | std::async (baseline) | Simpler; thread pool deferred pending profiling |
| 20 | Phase 3 parallelism | Per-shard vs per-term | Per-shard | Simpler; per-term is stretch goal |
| 21 | Query parsing | Not discussed → postfix | Postfix (shunting-yard) | Confirmed from PDF; standard Boolean query evaluation |
| 22 | Benchmarking approach | Built-in vs external scripts | External scripts | Portable across phases; clean separation |
| 23 | Shard lookup policy (Ph2) | Broadcast vs catalog vs bloom | Broadcast only (MVP) | Catalog and bloom are stretch goals |

---

## 15. Document Registry

All documents produced through Checkpoint 1:

| Document | File | Status |
|---|---|---|
| Phase 1 Architecture & Unit Design | `phase1_architecture.md` | Complete |
| Phase 1 Amendments | `phase1_amendments.md` | Complete |
| Phase 2 Architecture & Unit Design | `phase2_architecture.md` | Complete |
| Phase 3 Preliminary Architecture | `phase3_preliminary.md` | Intentionally incomplete |
| Benchmarking & Profiling Guide | `benchmarking_guide.md` | Complete |
| Project Log & Checkpoint 1 | `project_log_checkpoint1.md` | This document |

---

## 16. Signatures

This document represents a complete and accurate record of all design discussions, decisions, agreements, and open items from the start of the project through Checkpoint 1.

**Vedant Keshav Jadhav**  
MS CS, University of Arizona  
TA, CSC465 Reverse Engineering  
April 3, 2026

**Claude (Anthropic)**  
Design collaborator and sounding board  
April 3, 2026

---

*Next checkpoint to be created after Phase 1 implementation is complete and Phase 1 benchmarks are run.*
