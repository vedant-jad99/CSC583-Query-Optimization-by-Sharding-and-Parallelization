# Query Engine — Phase 3 Preliminary Architecture

**Project:** Query Optimization System with Parallelization and Sharded Indexing  
**Phase:** 3 — Parallel Query Execution  
**Status:** INCOMPLETE — To be solidified after Phase 1 and Phase 2 benchmarking  
**Author:** Vedant Keshav Jadhav  
**Date:** April 2026

---

## Important Note

This document is intentionally incomplete. Phase 3 design decisions — particularly around threading model and thread lifecycle management — will be informed by Phase 1 and Phase 2 benchmark and profiling results. Premature over-design risks optimising for the wrong bottleneck.

The core structural change of Phase 3 is known and documented here. The implementation details are marked as open TODOs with full tradeoff analysis, to be resolved once profiling data is available.

---

## 1. Phase 3 Objective

Phase 1 established the baseline single-process engine. Phase 2 introduced sharded indexes — smaller posting lists, parallel index construction, sequential query fan-out. Phase 3 takes the N `QueryRunner` instances from Phase 2 and executes them **concurrently across CPU cores** instead of sequentially.

**The single variable being introduced in Phase 3 is parallel query execution.** The index structure, shard count, merge strategies, and all other components remain unchanged. This isolation is deliberate — benchmark deltas are attributable specifically to parallelism.

**Expected gains:**
- Query latency reduction — N shards queried simultaneously instead of sequentially
- Throughput improvement — sustained queries per second under parallel execution
- p99 tail latency reduction — parallel execution reduces worst-case sequential accumulation

---

## 2. What is Known — Confirmed Design Decisions

---

### Decision 1 — True parallelism via CPU cores, not concurrency

C++ threads are native OS threads. Unlike Python's threading module, they are not subject to any GIL equivalent. Four threads in C++ map directly to four CPU cores — true parallel execution. No multiprocessing workaround needed.

This is the natural continuation of Phase 2's philosophy: Phase 2 used `ProcessPoolExecutor` in Python for true parallelism at index build time. Phase 3 uses C++ threads for true parallelism at query execution time.

---

### Decision 2 — Number of workers fixed at 4 (matching shard count)

One worker per shard. Four shards → four threads. This is the natural mapping — each thread is responsible for querying exactly one shard independently.

`N_WORKERS` will be made configurable via environment variable for benchmarking flexibility, matching the approach used for `N_SHARDS` in Phase 2.

---

### Decision 3 — No shared mutable state between threads

Each `QueryRunner` instance owns its own:
- `IRSubsystem` with its own const inverted index
- `OpHandler`
- Shard's const universal doc ID set

There is no shared mutable state between threads during query execution. This means Phase 3 requires **zero synchronisation primitives** (no mutexes, no locks, no atomics) during the query phase. The only coordination point is result collection after all threads complete.

This is a direct consequence of the Phase 2 architectural decision to give each `QueryRunner` full ownership of its shard's data.

---

### Decision 4 — Result ownership via future return values

Each thread returns an **owned** `vector<uint32_t>` — a copy of the `const vector<uint32_t>&` returned by its `QueryRunner`. This respects the const correctness contract from Phase 1 while giving the collecting thread an owned, non-const result it can pass to merge.

No pre-allocated shared result containers. No stale state between queries. Each query produces fresh owned vectors.

---

### Decision 5 — Merge unchanged from Phase 2

The merge step is identical to Phase 2 — both `PAIRWISE` and `PRIORITY_QUEUE` strategies, switchable via `MERGE_STRATEGY` environment variable. Merge runs on the main thread after all parallel query threads complete. No incremental or concurrent merging.

This keeps merge complexity out of Phase 3 and isolates the benchmarkable variable to parallel execution only.

---

### Decision 6 — Sequential queries, parallel execution within each query

Queries are processed one at a time from the caller's perspective. `BooleanEngine::query()` is synchronous — it blocks until all parallel shard queries complete and merge returns. The next query cannot begin until the current one fully resolves.

This avoids inter-query interference and keeps the execution model clean for benchmarking.

---

### Decision 7 — `std::async` as the baseline implementation

**What `std::async` is:**

`std::async` is a C++ standard library function that runs a callable asynchronously and returns a `std::future` holding the result. With `std::launch::async` policy, it spawns a thread immediately and runs the callable on it. When `.get()` is called on the future, the calling thread blocks until the async thread completes and retrieves the result.

**Why `std::async` over raw `std::thread` + join:**

| Concern | `std::thread` + join | `std::async` |
|---|---|---|
| Result collection | Requires shared container or manual sync | Future owns the result cleanly |
| Exception handling | Uncaught exception terminates program | Exceptions captured, re-thrown on `.get()` |
| Thread lifecycle | Manual — must join every thread | Automatic |
| Shared state | Required for results | Not required |
| Code complexity | Higher | Lower |
| Stale state risk | Yes, if container reused | No, fresh future per query |

**The baseline Phase 3 implementation:**

```cpp
auto normalized = preprocessor.process(raw_query);  // once

vector<future<vector<uint32_t>>> futures;
for (int i = 0; i < n_shards; i++) {
    futures.push_back(std::async(std::launch::async, [&, i]() {
        return vector<uint32_t>(queryRunners[i].query(normalized));
    }));
}

vector<vector<uint32_t>> shard_results;
for (auto& f : futures)
    shard_results.push_back(f.get());

return merge(shard_results);
```

**The honest caveat about `std::async`:**

`std::async` does not guarantee a persistent thread pool. Each call may spawn a fresh OS thread. Thread creation has measurable overhead — on Linux, spawning a thread costs roughly 10–50 microseconds. For N=4 per query, this is 40–200 microseconds of potential overhead per query on top of actual query execution time.

Whether this overhead is significant depends on query execution time, which depends on corpus size and query complexity. **This is exactly what Phase 1 and Phase 2 profiling will reveal.**

If profiling shows thread creation overhead is negligible relative to query execution time, `std::async` is the correct final implementation. If profiling shows it is significant, a persistent thread pool is warranted.

---

## 3. Open TODOs — To Be Resolved After Phase 1 and Phase 2 Benchmarking

---

### TODO 1 — Thread lifecycle model: `std::async` vs persistent thread pool

**Status:** Deferred pending profiling data.

**The question:** Is thread creation overhead per query significant enough to warrant a persistent thread pool?

**Option A — `std::async` (current baseline):**
Spawns threads per query. Simple, correct, standard library only. Thread creation overhead paid on every query.

**Option B — Persistent thread pool:**
4 worker threads live for the lifetime of `BooleanEngine`. Each query submits 4 tasks to the pool via a task queue. Threads pick up tasks, execute, signal completion via futures or condition variables. Main thread blocks until all 4 tasks complete.

Amortises thread creation cost across all queries. More complex to implement — requires a task queue, condition variables, and careful shutdown logic.

**How to decide:**
Run Phase 2 benchmarks. Profile query latency at the per-component level using `perf` or `callgrind`. If query execution time per shard is in the range of milliseconds, 50µs thread creation overhead is negligible — use `std::async`. If query execution time is in the range of microseconds (very fast queries on small shards), thread creation overhead dominates — use a thread pool.

**Benchmark signal to watch:**
- Phase 2 median query latency per shard
- If median shard query time < 500µs → thread pool warranted
- If median shard query time > 1ms → `std::async` is fine

---

### TODO 2 — Worker count: fixed 4 vs configurable vs hardware-detected

**Status:** Fixed at 4 for now, matching shard count. To be revisited.

**The question:** Should worker count always equal shard count, or should they be independently configurable?

For Phase 3 with N=4 shards and 4 workers the mapping is 1:1 and obvious. If shard count is later increased (e.g. N=8) but the laptop has 4 physical cores, having 8 threads fighting for 4 cores may hurt rather than help due to context switching overhead.

**TODO:** After Phase 2 benchmarking, experiment with `N_WORKERS` < `N_SHARDS` and benchmark the delta. This may become a Phase 3 sub-experiment.

---

### TODO 3 — Incremental merge vs post-completion merge

**Status:** Post-completion merge confirmed for now. Incremental merge deferred.

**The question:** Should merge begin as soon as any thread completes, overlapping merge with remaining thread execution?

**Current approach (post-completion):** Wait for all N threads to finish, then merge. Simple. Merge adds latency on top of the slowest thread.

**Alternative (incremental):** Merge shard results as each thread completes. The main thread monitors futures in completion order rather than submission order. Overlaps merge computation with remaining thread execution. May reduce total latency.

**How to decide:** Phase 3 profiling will reveal whether merge time is significant relative to query execution time. If merge is fast (microseconds), incremental merge adds complexity for negligible gain. If merge is slow (milliseconds for large result sets), incremental merge becomes worthwhile.

**Benchmark signal to watch:**
- Phase 2 merge time (pairwise vs priority queue) relative to query execution time
- If merge time < 10% of total query time → post-completion merge is fine
- If merge time > 10% of total query time → explore incremental merge

---

### TODO 4 — Exception handling across threads

**Status:** Deferred. `std::async` handles this via future exception propagation. Explicit strategy TBD.

**The question:** If one shard's query thread throws an exception, what should the engine do?

Options:
- Propagate exception to caller, abort query
- Return partial results from completed shards
- Retry failed shard

For Phase 3 this is unlikely to matter in practice. Flag for production hardening.

---

## 4. What Changes from Phase 2

### C++ — Changes

| Component | Status | Change |
|---|---|---|
| `Decompressor` | Unchanged | — |
| `Preprocessor` | Unchanged | — |
| `OpHandler` | Unchanged | — |
| `IRSubsystem` | Unchanged | — |
| `QueryRunner` | Unchanged | — |
| `BooleanEngine` | **Modified** | Sequential loop replaced with `std::async` fan-out |
| Merge strategies | Unchanged | Both pairwise and priority queue, same env flag |

**Python side: zero changes.** The sharding pipeline from Phase 2 is used as-is.

---

## 5. Preliminary Architecture Diagram

```
╔══════════════════════════════════════════════════════════════════════════════════╗
║                   PHASE 3 — PRELIMINARY ARCHITECTURE                           ║
║                   (subject to revision after profiling)                        ║
╚══════════════════════════════════════════════════════════════════════════════════╝

  Python pipeline: UNCHANGED from Phase 2
  shard_0.bin ... shard_N.bin: UNCHANGED from Phase 2

  QUERY TIME
 ┌─────────────────────────────────────────────────────────────────────────────┐
 │  C++ QUERY ENGINE                                                           │
 │                                                                             │
 │  BooleanEngine::query(raw_query)                                            │
 │    │                                                                        │
 │    ▼                                                                        │
 │  Preprocessor::process()  →  normalized_terms  (once)                      │
 │    │                                                                        │
 │    ▼                                                                        │
 │  std::async × N  (std::launch::async)                                      │
 │    │                                                                        │
 │    ├── Thread 0: queryRunners[0].query(normalized) → future<vector>        │
 │    ├── Thread 1: queryRunners[1].query(normalized) → future<vector>        │
 │    ├── Thread 2: queryRunners[2].query(normalized) → future<vector>        │
 │    └── Thread 3: queryRunners[3].query(normalized) → future<vector>        │
 │                                                                             │
 │    [all four threads execute concurrently on separate CPU cores]           │
 │                                                                             │
 │    ├── future[0].get() → owned vector<uint32_t>                            │
 │    ├── future[1].get() → owned vector<uint32_t>                            │
 │    ├── future[2].get() → owned vector<uint32_t>                            │
 │    └── future[3].get() → owned vector<uint32_t>                            │
 │                                                                             │
 │    ▼                                                                        │
 │  merge(shard_results)  [MERGE_STRATEGY env var]                            │
 │    ├── PAIRWISE:        O(M×N)   sequential two-way merge                  │
 │    └── PRIORITY_QUEUE:  O(M logN) k-way heap merge                         │
 │                                                                             │
 │    ▼                                                                        │
 │  const vector<uint32_t>&  →  result doc IDs                                │
 └─────────────────────────────────────────────────────────────────────────────┘

  ┌─────────────────────────────────────────────────────────────┐
  │  OPEN: thread lifecycle model                               │
  │  Current: std::async (spawns per query)         [baseline]  │
  │  Alternative: persistent thread pool            [TODO 1]    │
  │  Decision: defer to Phase 1/2 profiling                     │
  └─────────────────────────────────────────────────────────────┘
```

---

## 6. Benchmarking for Phase 3

The Phase 1 and Phase 2 benchmark framework is reused entirely.

### New Dimensions

**Thread model comparison** (if thread pool is implemented):

```
results/phase3/
├── async/          # std::async baseline
└── thread_pool/    # persistent thread pool (if warranted)
```

**Worker count experiment** (TODO 2):

```
results/phase3/
├── workers_2/
├── workers_4/
└── workers_8/
```

### Key Metrics to Watch

| Metric | What it reveals |
|---|---|
| Query latency vs Phase 2 | Raw gain from parallelism |
| p99 latency vs Phase 2 | Tail latency improvement |
| Throughput vs Phase 2 | Sustained capacity gain |
| Thread creation overhead | Whether thread pool is warranted (TODO 1) |
| Merge time vs query time | Whether incremental merge is warranted (TODO 3) |

### Profiling Signals That Drive TODO Resolution

Run `perf stat` and `callgrind` on Phase 3 engine. Look for:

- Time spent in thread creation vs query execution — resolves TODO 1
- Time spent in merge vs total query time — resolves TODO 3
- CPU utilisation across cores — confirms true parallelism is achieved

---

## 7. Decision Log — What Was Deliberately Deferred and Why

| Decision | Status | Reason for Deferral |
|---|---|---|
| Thread lifecycle: async vs thread pool | TODO 1 | Depends on per-shard query latency from Phase 2 benchmarks |
| Worker count independence from shard count | TODO 2 | Requires profiling to know optimal mapping |
| Incremental merge | TODO 3 | Depends on merge time relative to query time from profiling |
| Exception handling strategy | TODO 4 | Low priority for Phase 3; flag for hardening |

---

## 8. Implementer Checklist (Partial — To Be Completed)

```
CONFIRMED
[ ] std::async with std::launch::async for parallel fan-out
[ ] N futures collected, .get() called sequentially
[ ] Result copied from const return into owned vector inside lambda
[ ] Merge unchanged from Phase 2 — both strategies, same env flag
[ ] BooleanEngine::query() remains synchronous to caller
[ ] N_WORKERS environment variable added, default 4
[ ] Benchmark results written to results/phase3/

DEFERRED — PENDING PROFILING
[ ] TODO 1: Evaluate and optionally implement persistent thread pool
[ ] TODO 2: Evaluate independent N_WORKERS vs N_SHARDS configuration
[ ] TODO 3: Evaluate incremental merge implementation
[ ] TODO 4: Define exception handling strategy across threads
```
