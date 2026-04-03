# Query Engine — Phase 1 Architecture & Unit Design

**Project:** Query Optimization System with Parallelization and Sharded Indexing  
**Phase:** 1 — Static Boolean Query Engine  
**Author:** Vedant Keshav Jadhav  
**Date:** April 2026

---

## Overview

Phase 1 is a static, Boolean query engine. The Python pipeline runs once at build time, producing a compressed binary index. The C++ query engine loads it at startup and serves Boolean queries. No ranking, no positional indexing, no dynamic updates.

```
┌─────────────────────────────────────────────────────────────┐
│                     BUILD TIME (Python)                   │
│                                                           │
│   Raw Documents → Pipeline → index.bin                    │
└─────────────────────────────┬───────────────────────────────┘
                              │
                         index.bin
                              │
┌─────────────────────────────▼───────────────────────────────┐
│                   QUERY TIME (C++)                        │
│                                                           │
│   index.bin → BooleanEngine → query results               │
└─────────────────────────────────────────────────────────────┘
```

---

## Part 1 — Python Indexing Pipeline

### Class Hierarchy

```
Pipeline
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

#### `FileReader`
- **Responsibility:** Read raw documents from disk
- **Input:** Directory path or file list
- **Output:** `(doc_id, raw_text)` stream
- **Notes:** Assigns sequential integer doc IDs. Abstracts file format (plaintext for Phase 1)

---

#### `Tokenizer`
- **Responsibility:** Split raw text into tokens
- **Input:** Raw text string
- **Output:** List of token strings
- **Notes:** Whitespace and punctuation boundary splitting

---

#### `Normalizer`
- **Responsibility:** Orchestrates the full normalization pipeline
- **Owns:** `CaseFolder`, `PunctuationRemover`, `StopWordFilter`, `Stemmer`
- **Input:** Token list
- **Output:** Normalized token list
- **Pipeline order:** CaseFold → PunctuationRemove → StopWordFilter → Stem

**`CaseFolder`** — lowercases all tokens

**`PunctuationRemover`** — strips non-alphanumeric characters from tokens, drops empty results

**`StopWordFilter`** — filters tokens against a stop word list (static file or hardcoded set for Phase 1)

**`Stemmer`** — applies Porter stemmer (or Snowball). **Must match exactly what `Preprocessor` does in C++**

---

#### `IndexBuilder`
- **Responsibility:** Build the in-memory inverted index
- **Input:** Stream of `(doc_id, normalized_tokens)`
- **Output:** `dict[str, list[int]]` — term → sorted list of doc IDs
- **Notes:** Deduplicates doc IDs per term. Posting lists must be sorted (required for delta encoding downstream)

---

#### `IndexCreator`
- **Responsibility:** Orchestrate document ingestion → index construction
- **Owns:** `FileReader`, `Tokenizer`, `Normalizer`, `IndexBuilder`
- **Output:** Inverted index passed to `Pipeline`

---

#### `VBEncoder`
- **Responsibility:** Delta encode then VByte encode a posting list
- **Input:** Sorted `list[int]` of doc IDs
- **Output:** `bytes`
- **Notes:**
  - Delta encode first: store differences between consecutive doc IDs
  - Then VByte encode each delta
  - First doc ID stored as-is (delta from 0)

**VByte encoding scheme:**
```
For each value:
  while value > 127:
    emit (value & 0x7F)        # lower 7 bits, continuation bit = 0
    value >>= 7
  emit (value | 0x80)          # final byte, continuation bit = 1
```

---

#### `BinWriter`
- **Responsibility:** Write the binary index file in the agreed format
- **Input:** Inverted index, output path
- **Owns:** `VBEncoder`
- **Endianness:** Little-endian throughout (`struct` with `<` prefix in Python)

**Bin file format:**
```
[8  bytes]  Magic string + version          e.g. "QEIDX\x00\x01\x00"
[4  bytes]  Number of terms                 uint32 LE
── per term (repeats for all terms) ──────────────────────────
[2  bytes]  Term length (M)                 uint16 LE
[4  bytes]  Doc ID count (N)                uint32 LE
[M  bytes]  Term string                     UTF-8, no null terminator
[N  bytes]  VByte-encoded delta doc IDs
──────────────────────────────────────────────────────────────
[4  bytes]  CRC32 checksum (optional)       uint32 LE
```

---

#### `MakeBinFile`
- **Responsibility:** Serialize and write the index to disk
- **Owns:** `VBEncoder`, `BinWriter`
- **Input:** Inverted index from `IndexCreator`
- **Output:** `index.bin`

---

#### `Pipeline`
- **Responsibility:** Top-level orchestrator
- **Owns:** `IndexCreator`, `MakeBinFile`
- **Execution flow:**
```
1. IndexCreator.run(corpus_path)  →  inverted_index
2. MakeBinFile.write(inverted_index, output_path)  →  index.bin
```
- Entry point invoked by Makefile/CMake pre-build step

---

### Build Integration

**Makefile target:**
```makefile
index.bin:
    python3 pipeline/pipeline.py --corpus $(CORPUS_DIR) --out index.bin

build: index.bin
    cmake --build .
```

> CMake alternative via `add_custom_command` with `PRE_BUILD` is possible but Makefile is simpler and more portable here.

---

## Part 2 — C++ Query Engine

### Class Hierarchy

```
main.cpp
└── BooleanEngine
    ├── Decompressor        (decompressor.hpp / decompressor.cpp)
    └── QueryRunner
        ├── Preprocessor
        └── IRSubsystem
            └── OpHandler
```

---

### Unit Specifications

---

#### `Decompressor` — `decompressor.hpp` / `decompressor.cpp`
- **Responsibility:** Parse `index.bin`, reconstruct inverted index and universal doc ID set
- **Init:** `load(const std::string& path)`
- **Internally:**
  - `mmap` the file → raw `uint8_t*` pointer
  - Walk pointer: validate magic, read num_terms
  - Per term: read term_len, doc_cnt, term string, VByte decode + delta expand doc IDs
  - Accumulate all doc IDs into universal set as a byproduct
  - `munmap` on completion
- **Exposes:**
  - `getIndex()` → `unordered_map<string, vector<uint32_t>>&&`
  - `getDocIDs()` → `set<uint32_t>&&`
- **Notes:** Both getters return rvalue references to enable `std::move` at handoff. After move, Decompressor internals are empty — intentional.

> **On `mmap`:** Maps the file directly into the process's virtual address space. No kernel→userspace copy, no explicit `read()` syscalls. For a static, read-once, sequential parse like this — ideal. POSIX only (Linux/macOS); Windows would require `CreateFileMapping`.

**VByte decode + delta expand:**
```
read bytes until continuation bit = 1
reconstruct value from 7-bit groups
accumulate delta: doc_id = prev_doc_id + delta
```

**Universal doc ID set (NOT operation support):**  
Built on the fly during parse — union of all posting lists. A document absent from all posting lists would be one with no indexable tokens (pure stop words), which is practically irrelevant for any query.

---

#### `Preprocessor`
- **Responsibility:** Mirror Python normalization exactly for query terms
- **Operations:** tokenize → case fold → punctuation remove → stop word filter → stem
- **Must use same stemmer algorithm as Python side (Porter)**
- **Input:** Raw query string
- **Output:** `vector<string>` of normalized terms

---

#### `OpHandler`
- **Responsibility:** Execute Boolean set operations on posting lists
- **All operations work on** `const vector<uint32_t>&`
- **Operations:**
  - `AND(list_a, list_b)` → sorted intersection
  - `OR(list_a, list_b)` → sorted union
  - `NOT(list, universal_set)` → set difference against universal doc ID set
- **Returns:** `vector<uint32_t>` (owned result)
- **Notes:** Since posting lists are sorted, AND and OR run as linear merge — O(m+n), no hash overhead

---

#### `IRSubsystem`
- **Responsibility:** Execute a full parsed query against the index
- **Instantiation params:** `const unordered_map<string, vector<uint32_t>>&`, `const set<uint32_t>&`
- **Owns:** `OpHandler`
- **Holds** index and docID set as `const` references after `std::move` handoff
- **Flow:** receive parsed query → look up posting lists → delegate to `OpHandler` → return results
- **Returns:** `const vector<uint32_t>&`

---

#### `QueryRunner`
- **Responsibility:** Accept raw query string, preprocess, execute, return results
- **Constructor:** instantiates `Preprocessor`
- **`init(index, docIDs)`:** instantiates `IRSubsystem` with moved-in index and docIDs
- **Flow:**
```
raw query → Preprocessor → normalized terms + operators
                         → IRSubsystem → result doc IDs
```

---

#### `BooleanEngine`
- **Responsibility:** Top-level C++ orchestrator
- **Owns:** `Decompressor`, `QueryRunner`
- **Constructor:** instantiates `QueryRunner`
- **`init(const std::string& bin_path)`:**
```cpp
decompressor.load(bin_path);
queryRunner.init(
    std::move(decompressor.getIndex()),
    std::move(decompressor.getDocIDs())
);
```
- **`query(const std::string& raw_query)`** → delegates to `QueryRunner`

---

#### `main.cpp`
```cpp
BooleanEngine engine;
engine.init("index.bin");
// query loop
auto results = engine.query("information AND retrieval NOT theory");
```

---

### Const Correctness Contract

| Object | Type |
|---|---|
| Inverted index in IRSubsystem | `const unordered_map<string, vector<uint32_t>>` |
| Universal doc ID set | `const set<uint32_t>` |
| Posting list lookups | `const vector<uint32_t>&` |
| Query results returned | `const vector<uint32_t>&` |
| All OpHandler inputs | `const vector<uint32_t>&` |

---

## Complete Architecture Diagram

```
╔═════════════════════════════════════════════════════════════════════════════════════╗
║                          PHASE 1 — COMPLETE ARCHITECTURE                          ║
╚═════════════════════════════════════════════════════════════════════════════════════╝

  BUILD TIME
 ┌─────────────────────────────────────────────────────────────────────────────────┐
 │  PYTHON INDEXING PIPELINE                                                     │
 │                                                                               │
 │  ┌──────────────────────────────────────────────────────────────────────────┐   │
 │  │  Pipeline                                                              │   │
 │  │                                                                        │   │
 │  │  ┌───────────────────────────────────────┐  ┌──────────────────────┐     │   │
 │  │  │  IndexCreator                        │  │  MakeBinFile         │    │   │
 │  │  │                                      │  │                      │    │   │
 │  │  │  ┌───────────┐                       │  │  ┌───────────────┐    │    │   │
 │  │  │  │ FileReader│                       │  │  │  VBEncoder    │   │    │   │
 │  │  │  │           │ (doc_id, raw_text)    │  │  │               │   │    │   │
 │  │  │  │ corpus/ ──┼──────────────────┐    │  │  │ delta encode  │    │    │   │
 │  │  │  └───────────┘                  │    │  │  │ VByte encode  │    │    │   │
 │  │  │                                      │  │  └───────┬───────┘    │    │   │
 │  │  │  ┌───────────┐           ┌──────────┐ │  │          │           │    │   │
 │  │  │  │ Tokenizer │──────────►│Normalizer│ │  │  ┌───────▼───────┐   │    │   │
 │  │  │  └───────────┘  tokens   │          │ │  │  │   BinWriter   │   │    │   │
 │  │  │                          │CaseFolder│ │  │  │               │   │    │   │
 │  │  │                          │PunctRem. │ │  │  │ magic+version │   │    │   │
 │  │  │                          │StopWords │ │  │  │ num_terms     │   │    │   │
 │  │  │                          │Stemmer   │ │  │  │ per term:     │   │    │   │
 │  │  │                          └────┬─────┘ │  │  │  term_len     │   │    │   │
 │  │  │                               │       │  │  │  doc_cnt      │   │    │   │
 │  │  │                    norm tokens▼       │  │  │  term str     │   │    │   │
 │  │  │  ┌──────────────┐                     │  │  │  VB doc IDs   │   │    │   │
 │  │  │  │ IndexBuilder │                     │  │  └───────────────┘   │    │   │
 │  │  │  │              │                     │  │                      │   │   │
 │  │  │  │ dict[str,    │                     │  └──────────────────────┘    │   │
 │  │  │  │ list[int]]   │                     │             │               │   │
 │  │  │  └──────────────┘                     │             │               │   │
 │  │  └───────────────────────────────────────┘             │                │   │
 │  │                │                                       │               │   │
 │  │                │   inverted index                      │               │   │
 │  │                └───────────────────────────────────────┘                │   │
 │  └──────────────────────────────────────────────────────────────────────────┘   │
 │                                          │                                    │
 │               Makefile: python3 pipeline.py --corpus ./docs --out index.bin   │
 └──────────────────────────────────────────┼──────────────────────────────────────┘
                                            │
                                            ▼
                              ┌─────────────────────────┐
                              │        index.bin        │
                              │                         │
                              │  [8B]  magic + version  │
                              │  [4B]  num_terms        │
                              │  ── per term ────────── │
                              │  [2B]  term_len         │
                              │  [4B]  doc_cnt          │
                              │  [MB]  term string      │
                              │  [NB]  VByte doc IDs    │
                              │  ────────────────────   │
                              │  [4B]  checksum (opt)   │
                              └─────────────┬───────────┘
                                            │
                                            │  mmap
  QUERY TIME                                │
 ┌──────────────────────────────────────────┼──────────────────────────────────────┐
 │  C++ QUERY ENGINE                        │                                    │
 │                                          ▼                                    │
 │  ┌──────────────────────────────────────────────────────────────────────────┐   │
 │  │  main.cpp                                                              │   │
 │  │  BooleanEngine engine;                                                 │   │
 │  │  engine.init("index.bin");    engine.query("X AND Y NOT Z");           │   │
 │  └─────────────────────────────────────┬────────────────────────────────────┘   │
 │                                        │                                      │
 │                                        ▼                                      │
 │  ┌──────────────────────────────────────────────────────────────────────────┐   │
 │  │  BooleanEngine                                                          │  │
 │  │                                                                         │  │
 │  │  init(path):                                                            │  │
 │  │    decompressor.load(path)                                              │  │
 │  │    queryRunner.init(std::move(index), std::move(docIDs))                │  │
 │  │                                                                         │  │
 │  │  ┌──────────────────────────┐      ┌──────────────────────────────────┐   │  │
 │  │  │  Decompressor            │      │  QueryRunner                    │  │  │
 │  │  │  decompressor.hpp/.cpp   │      │                                 │  │  │
 │  │  │                          │      │  ┌────────────────────────────┐  │  │  │
 │  │  │  load(path):             │      │  │  Preprocessor              │ │  │  │
 │  │  │    mmap bin file         │      │  │                            │ │  │  │
 │  │  │    validate magic        │      │  │  tokenize()                │ │  │  │
 │  │  │    walk pointer          │      │  │  casefold()     mirrors    │ │  │  │
 │  │  │    VByte decode          │      │  │  punct_remove() Python     │ │  │  │
 │  │  │    delta expand          │      │  │  stopword()     pipeline   │ │  │  │
 │  │  │    build index           │      │  │  stem()                    │ │  │  │
 │  │  │    build docID set       │      │  └────────────────────────────┘  │  │  │
 │  │  │    munmap                │      │                                 │  │  │
 │  │  │                          │      │  ┌────────────────────────────┐  │  │  │
 │  │  │  getIndex()  ─────────── ┼─move─┼─►│  IRSubsystem               │  │  │  │
 │  │  │  getDocIDs() ─────────── ┼─move─┼─►│                            │  │  │  │
 │  │  │                          │      │  │  const unordered_map       │  │ │  │
 │  │  └──────────────────────────┘       │  │  <string,vector<uint32_t>> │  │ │  │
 │  │                                    │  │                            │  │ │  │
 │  │                                    │  │  const set<uint32_t>       │  │ │  │
 │  │                                    │  │                            │  │ │  │
 │  │                                    │  │  ┌──────────────────────┐   │  │ │  │
 │  │                                    │  │  │  OpHandler           │  │  │ │  │
 │  │                                    │  │  │                      │  │  │ │  │
 │  │                                    │  │  │  AND → linear merge  │  │  │ │  │
 │  │                                    │  │  │  OR  → linear merge  │  │  │ │  │
 │  │                                    │  │  │  NOT → set diff      │  │  │ │  │
 │  │                                    │  │  │        vs univ set   │  │  │ │  │
 │  │                                    │  │  └──────────────────────┘  │  │ │   │
 │  │                                    │  └────────────────────────────┘  │ │   │
 │  │                                    └──────────────────────────────────┘ │   │
 │  └──────────────────────────────────────────────────────────────────────────┘   │
 │                                        │                                      │
 │                                        ▼                                      │
 │                           const vector<uint32_t>&                             │
 │                               result doc IDs                                  │
 └─────────────────────────────────────────────────────────────────────────────────┘

 CONST CORRECTNESS CONTRACT
 ┌─────────────────────────────────────────────────────────────┐
 │  inverted index in IRSubsystem  →  const unordered_map    │
 │  universal doc ID set           →  const set<uint32_t>    │
 │  posting list lookups           →  const vector<uint32_t>&│
 │  OpHandler inputs               →  const vector<uint32_t>&│
 │  query results                  →  const vector<uint32_t>&│
 └─────────────────────────────────────────────────────────────┘
```

---

## Data Flow Summary

```
corpus/
  └── docs          →  FileReader
                    →  Tokenizer
                    →  Normalizer (fold → punct → stopword → stem)
                    →  IndexBuilder
                    →  dict[str, list[int]]
                    →  VBEncoder (delta + VByte)
                    →  BinWriter
                    →  index.bin

index.bin           →  Decompressor (mmap)
                    →  unordered_map + set<uint32_t>
                    →  std::move → IRSubsystem

raw query           →  Preprocessor (mirrors Python exactly)
                    →  normalized terms + operators
                    →  IRSubsystem + OpHandler
                    →  result doc IDs
```

---

## Key Design Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Retrieval model | Boolean (AND/OR/NOT) | Clean baseline for benchmarking sharding/parallelism in later phases |
| Compression | VByte with delta encoding | Simple, fast, well-understood. Sorted posting lists required |
| Endianness | Little-endian | Uniform across Python (struct `<`) and C++ (x86) |
| File I/O in C++ | `mmap` | Eliminates kernel→userspace copy, OS handles prefetch, minimal init latency |
| Index mutability | Static (write-once) | Simplifies design; no concurrent write concerns |
| Universal set for NOT | Built on-the-fly in Decompressor | Avoids bin file bloat; missing-doc edge case negligible in practice |
| Stop words | Removed at index time | Prevents enormous posting lists for high-frequency terms |
| Ownership transfer | `std::move` at `BooleanEngine::init()` | Single owner after init, zero data copies |
