# Query Engine — Phase 1 Amendments

**Project:** Query Optimization System with Parallelization and Sharded Indexing  
**Document Type:** Amendment Record  
**Author:** Vedant Keshav Jadhav  
**Date:** April 2026

---

## Purpose of This Document

This document records all amendments to the Phase 1 design that were identified during Phase 2 scoping. These are not bugs or mistakes in the Phase 1 design — they are deliberate forward-looking changes made to ensure Phase 1 is cleanly extensible into Phase 2 and Phase 3 without requiring rewrites of core components.

Each amendment includes the original design, the change, and the full rationale.

**All changes described here must be implemented as part of Phase 1.** They are prerequisites for Phase 2 to work correctly and cleanly.

---

## Amendment 1 — Corpus Presorting and Doc ID Offset Logic

### Original Phase 1 Design

In Phase 1, the `Pipeline` class reads documents from the corpus directory and assigns sequential integer doc IDs starting from 0. The assignment happens organically as `FileReader` encounters files — the order of file discovery (which depends on the OS filesystem, directory traversal order, or Python's `os.listdir()`) determines which document gets which ID.

This works correctly in Phase 1 because there is only one pipeline and one index. The doc ID space is unified and consistent by definition.

### The Problem This Creates in Phase 2

In Phase 2, the corpus is split across N shards. Each shard is built by an independent `Pipeline` instance running in a separate process. If each pipeline assigns doc IDs starting from 0 independently, the following happens:

```
Shard 0 pipeline: assigns doc IDs 0, 1, 2, 3 ...
Shard 1 pipeline: assigns doc IDs 0, 1, 2, 3 ...
Shard 2 pipeline: assigns doc IDs 0, 1, 2, 3 ...
Shard 3 pipeline: assigns doc IDs 0, 1, 2, 3 ...
```

Doc ID 5 in Shard 0 and doc ID 5 in Shard 1 are completely different documents. When the C++ engine merges query results across shards, it has no way to distinguish them. The merged result set is corrupt — duplicate IDs referring to different documents.

### The Fix

**Two changes are required:**

#### Change 1A — Presort the corpus file list

Before any pipeline runs, the full corpus file list must be sorted in a deterministic, reproducible order. Sorting by filename or full path alphabetically is sufficient.

This sorting must happen **once**, at the top level, before any shard assignment or pipeline instantiation. The sorted list is the authoritative ordering of all documents in the corpus.

This is implemented as a standalone function in `pipeline.py` (the entry point), not as a class. It is a utility step, not a domain object.

```python
def presort_corpus(corpus_dir: str) -> list[str]:
    files = [
        os.path.join(corpus_dir, f)
        for f in os.listdir(corpus_dir)
        if os.path.isfile(os.path.join(corpus_dir, f))
    ]
    return sorted(files)
```

**Why sorting, not hashing?**

An alternative considered was pre-hashing document filenames to integer IDs and saving the mapping to a JSON file. This was rejected for the following reason:

The algorithmic complexity of the JSON approach is O(1) per lookup, which appears superior to O(N log N) for sorting. However, this analysis is incomplete. The O(1) lookup only applies after the JSON has been written to disk (O(N) + I/O), read back from disk (O(N) + I/O), and parsed (O(N)). The total cost of the JSON approach is O(N) with significant disk I/O constants. The total cost of sorting is O(N log N) entirely in memory with zero disk I/O.

In practice, for any realistic corpus size in this project, O(N log N) in-memory computation is faster than O(N) disk I/O by orders of magnitude. Disk I/O constants are 100–1000x larger than in-memory computation constants. Sorting wins on practical performance.

Additionally, sorting requires no extra files to manage, no extra parsing, and no external dependency. For a static corpus — which this project uses — sorting is the correct and simpler choice.

#### Change 1B — Pipeline accepts a file slice and a doc ID offset

The `Pipeline` class is modified to accept two additional parameters:

- `file_slice: list[str]` — the subset of the sorted corpus file list assigned to this pipeline
- `doc_id_offset: int` — the starting doc ID for this pipeline's documents

Doc IDs are then assigned as `doc_id_offset + local_index` where `local_index` is the position of the document within this pipeline's file slice.

```
Total corpus: 100,000 documents, 4 shards, 25,000 docs per shard

Shard 0: file_slice = files[0:25000],     doc_id_offset = 0
Shard 1: file_slice = files[25000:50000], doc_id_offset = 25000
Shard 2: file_slice = files[50000:75000], doc_id_offset = 50000
Shard 3: file_slice = files[75000:100000],doc_id_offset = 75000
```

Result: every doc ID across all shards is globally unique. Shard 1's first document gets ID 25000, not ID 0. Merging results across shards is a clean set operation with no ID conflicts.

**Why at the Pipeline level, not FileReader level?**

The offset is a coordination concern — it is determined by the sharding strategy, not by the file reading process. Keeping it at `Pipeline` level means `FileReader` remains a simple, dumb file reader with no knowledge of sharding. The coordination logic lives where it belongs: at the orchestration layer.

### Impact on Phase 1 Single-Pipeline Execution

For Phase 1, `Pipeline` is called with `file_slice = all_files` and `doc_id_offset = 0`. Behaviour is identical to the original design. No functional change for Phase 1.

---

## Amendment 2 — Preprocessor Decoupled from QueryRunner and Owned by BooleanEngine

### Original Phase 1 Design

In Phase 1, `QueryRunner` owns the `Preprocessor`. The flow is:

```
BooleanEngine.query(raw_query)
  → QueryRunner.query(raw_query)
      → Preprocessor.process(raw_query) → normalized terms
      → IRSubsystem.execute(normalized_terms) → results
```

`Preprocessor` sits inside `QueryRunner`. When `BooleanEngine` calls `QueryRunner`, it passes the raw query string, and `QueryRunner` handles normalization internally.

### The Problem This Creates in Phase 2

In Phase 2, `BooleanEngine` owns N `QueryRunner` instances — one per shard. If `Preprocessor` remains inside `QueryRunner`, the following happens for every query:

```
BooleanEngine.query(raw_query)
  → QueryRunner_0.query(raw_query) → Preprocessor_0.process(raw_query) → normalized terms
  → QueryRunner_1.query(raw_query) → Preprocessor_1.process(raw_query) → normalized terms
  → QueryRunner_2.query(raw_query) → Preprocessor_2.process(raw_query) → normalized terms
  → QueryRunner_3.query(raw_query) → Preprocessor_3.process(raw_query) → normalized terms
```

The same raw query is preprocessed four times, producing identical results each time. This is pure redundant computation. Preprocessing — tokenization, case folding, punctuation removal, stop word filtering, stemming — is not free. Doing it N times for N shards is wasteful and gets worse as N increases.

Additionally, having N `Preprocessor` instances means N copies of the stop word list and stemmer state in memory — another unnecessary overhead.

### The Fix

`Preprocessor` is moved out of `QueryRunner` and into `BooleanEngine`. `BooleanEngine` preprocesses the raw query exactly once and passes the normalized terms to each `QueryRunner`.

`QueryRunner` is modified to accept normalized terms directly instead of a raw query string.

```
BooleanEngine.query(raw_query)
  → Preprocessor.process(raw_query) → normalized_terms   ← happens once
  → QueryRunner_0.query(normalized_terms) → results_0
  → QueryRunner_1.query(normalized_terms) → results_1
  → QueryRunner_2.query(normalized_terms) → results_2
  → QueryRunner_3.query(normalized_terms) → results_3
  → merge(results_0..3) → final results
```

One `Preprocessor` instance. One preprocessing pass per query. Clean.

### Why This is Also Better Design in Phase 1

Even ignoring Phase 2, this is a better separation of concerns. Preprocessing is a concern of the query engine as a whole — it is about understanding and normalizing the user's input. It is not a concern of the query runner, which should only be responsible for executing a query against an index.

`BooleanEngine` is the right owner because it is the top-level coordinator that understands the full query lifecycle: receive raw input → normalize → execute → return results.

### Impact on Phase 1

In Phase 1, `BooleanEngine` owns exactly one `QueryRunner`. The flow becomes:

```
BooleanEngine.query(raw_query)
  → Preprocessor.process(raw_query) → normalized_terms
  → QueryRunner.query(normalized_terms) → results
```

Functionally identical to the original, with one preprocessing pass. The only structural change is that `Preprocessor` is instantiated in `BooleanEngine` rather than `QueryRunner`.

**This change must be implemented in Phase 1** so that Phase 2 requires no modification to `QueryRunner` or `IRSubsystem`.

---

## Amendment Summary

| Amendment | Component | Change | Reason | Implemented In |
|---|---|---|---|---|
| 1A | `pipeline.py` entry point | Add presort function for corpus files | Ensures deterministic, globally consistent doc ID assignment across shards | Phase 1 |
| 1B | `Pipeline` class | Accept `file_slice` and `doc_id_offset` parameters | Enables globally unique doc IDs across N shards without coordination at runtime | Phase 1 |
| 2 | `Preprocessor` | Move from `QueryRunner` to `BooleanEngine` | Eliminates redundant preprocessing across N shards; better separation of concerns | Phase 1 |

---

## Checklist for Implementers

```
[ ] presort_corpus() function added to pipeline.py entry point
[ ] Pipeline.__init__() accepts file_slice and doc_id_offset
[ ] Pipeline uses doc_id_offset when assigning doc IDs during indexing
[ ] Phase 1 single-pipeline call passes full file list and offset=0
[ ] Preprocessor removed from QueryRunner
[ ] Preprocessor instantiated in BooleanEngine constructor
[ ] BooleanEngine.query() preprocesses raw query before passing to QueryRunner
[ ] QueryRunner.query() accepts normalized terms, not raw string
[ ] All existing Phase 1 behaviour verified unchanged after amendments
```
