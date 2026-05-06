# CSC583 — Query Optimization via Sharding and Parallelization

A three-phase Boolean Information Retrieval engine demonstrating the performance impact of index sharding and parallel query execution. Built from scratch in C++ and Python, without third-party IR libraries.

**[Project Report](report.pdf)** · **[Architecture Docs](docs/)** · **[Benchmark Results](benchmark/results/)**

---

## Architecture

| Phase | Index | Query Execution | Merge |
|---|---|---|---|
| 1 | Single `index.bin` | Sequential, single engine | — |
| 2 | N `shard_i.bin` files | Sequential fan-out across N engines | O(M) tail join |
| 3 | N `shard_i.bin` files | Parallel, persistent thread pool | O(M) tail join |

The Python pipeline handles corpus ingestion, normalization (case-fold → punctuation removal → stop-word filter → Porter stemming), VByte+delta index encoding, and shard construction via `ProcessPoolExecutor`. The C++ engine handles mmap-based loading and postfix Boolean query evaluation.

---

## Requirements

- **C++17** — `g++` or `clang++`
- **Python 3.9+**
- **make**
- macOS or Linux — tested on Apple Silicon (macOS) and Ubuntu 22.04

Python dependencies (NLTK etc.) are installed automatically by `make` on first run.

---

## Building and Running

Place your corpus under `data.nosync/<corpus_name>/` (one document per file). The `CORPUS` flag specifies the directory name. The Makefile handles venv creation, dependency installation, index building, and compilation in a single command.

### Phase 1 — Single index, sequential engine

```bash
make clean && make PHASE=1 CORPUS=<corpus_name>
./run_engine index.bin --interactive
```

### Phase 2 — Sharded index, sequential query fan-out

```bash
make clean && make PHASE=2 CORPUS=<corpus_name>
./run_engine shards/ --shards 4 --interactive
```

### Phase 3 — Sharded index, parallel query execution

```bash
make clean && make PHASE=3 CORPUS=<corpus_name>
./run_engine shards/ --shards 4 --interactive
```

### Query syntax

Queries use **postfix (RPN) notation**. Supported operators: `\and`, `\or`, `\not`.

```
Query > relativity quantum \and
Query > time world \or people \or
Query > government law \and military \not
Query > q
```

---

## Benchmarking

Run the full benchmark suite for a given phase. Results are written to `benchmark/results/phase{N}/` and plots to `benchmark/results/plots/`.

```bash
# Phase 1
make bench BENCH_PHASE=1 CORPUS=<corpus_name>

# Phase 2 — 4 shards
make bench BENCH_PHASE=2 CORPUS=<corpus_name> N_SHARDS=4

# Phase 3 — 4 shards
make bench BENCH_PHASE=3 CORPUS=<corpus_name> N_SHARDS=4

# Cross-phase comparison
make bench-report BENCH_PHASE="1 2 3"
```

Individual benchmark targets: `bench-indexing`, `bench-init`, `bench-query`, `bench-memory`, `bench-report`.

---

## Preparing a Large Corpus (WikiText-103)

The data directory contains the files for import large datasets. The two datasets are:

1. A 100k documents large dataset. To get the dataset, unzip the `input.7z` file to a suitable directory.

2. The wikitext-103 dataset. This contains ~1M documents. To install, run the below commands:
```bash
pip install datasets
python3 data.nosync/prepare_wikitext103.py --out-dir data.nosync/wikitext

# Limit to N docs for a quick test run
python3 data.nosync/prepare_wikitext103.py --out-dir data.nosync/wikitext --limit 100000
```

** Note **: It is imperative to download one of these datasets as the queries composed for bechmarking
are based on these datasets.

Then build with `CORPUS=wikitext`.

---

## Key Results (859,955-document corpus)

| Metric | Phase 1 | Phase 2 | Phase 3 |
|---|---|---|---|
| Build time | 116.3s | 32.4s **(3.59×)** | 32.5s **(3.58×)** |
| Init time | 2521ms | 2546ms | 663ms **(3.80×)** |
| Complex query median | 1.93ms | 1.97ms | 1.15ms **(1.67×)** |
| Complex QPS | 192 | 186 | **253** |

---

## Cleaning Up

```bash
make clean          # remove binaries, index, shards
make clean-venv     # remove Python virtual environment
make clean-shards   # remove shard files only
```

---

## Repository Structure

```
.
├── src/
│   ├── boolean_engine.cpp    # Phase 1 engine
│   ├── master_engine.cpp     # Phase 2/3 engine (MasterEngine)
│   ├── ir_system.cpp         # IRSystem, QueryRunner, postfix evaluator
│   ├── decompressor.cpp      # mmap-based index loader
│   └── main.cpp              # Entry point, CLI parsing
├── includes/                 # C++ headers
├── scripts/
│   ├── main.py               # Phase 1 pipeline entry point
│   ├── main_sharded.py       # Phase 2/3 pipeline entry point
│   └── pipeline/             # IndexCreator, ShardBuilder, VBEncoder, etc.
├── benchmark/
│   ├── queries/              # short.txt, medium.txt, complex.txt
│   ├── bench_init.py
│   ├── bench_query.py
│   ├── bench_indexing.py
│   ├── bench_memory.sh
│   └── report.py
├── docs/                     # Architecture documents per phase
│   └── records/              # Records/checkpoints after design decisions
├── tests/                    # C++ and Python unit tests
└── Makefile
```

---

## Documentation

- **Phase 1 Architecture**: [`docs/records/phase1_architecture.md`](docs/records/phase1_architecture.md)
- **Phase 2 Architecture**: [`docs/records/phase2_architecture.md`](docs/records/phase2_architecture.md)
- **Benchmarking Analysis**: [`docs/records/benchmarking_analysis.md`](docs/records/benchmarking_analysis.md)
- **Project Report**: [`docs/report.pdf`](docs/report.pdf)
