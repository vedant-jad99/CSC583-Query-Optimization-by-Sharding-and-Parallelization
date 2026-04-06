"""
pipeline.py
───────────
Top-level orchestrator and entry point for the Phase 1 Python indexing pipeline.

Execution flow:
    1. presort_corpus(corpus_dir)  →  deterministic sorted file list
    2. Pipeline(file_slice, doc_id_offset=0)
    3. IndexCreator.run()          →  inverted_index
    4. MakeBinFile.write(index)    →  index.bin

Usage:
    python3 pipeline.py --corpus <corpus_dir> --out <output_path>

Ownership:
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
    └── MakeBinFile          (implemented by teammates)
        └── BinWriter
            └── VBEncoder

Phase 1 Amendments implemented:
    - presort_corpus() for deterministic doc ID assignment
    - Pipeline accepts file_slice and doc_id_offset for Phase 2 compatibility

Author: Chinmay Mhatre
Phase:  1
"""

import argparse
import os
import sys

from index_creator import IndexCreator
from make_bin_file import MakeBinFile


# ── Corpus presorting (Phase 1 amendment 1A) ──────────────────────────── #

def presort_corpus(corpus_dir: str) -> list[str]:
    """
    Produce a deterministic, globally consistent ordering of all corpus documents.

    Sort key: full file path, alphabetical.
    Must be called exactly once before any Pipeline instantiation.
    The sorted list is the authoritative document ordering for the entire system.

    Args:
        corpus_dir: Path to the corpus directory.

    Returns:
        Sorted list of absolute file paths (directories excluded).
    """
    files: list[str] = [
        os.path.join(corpus_dir, f)
        for f in os.listdir(corpus_dir)
        if os.path.isfile(os.path.join(corpus_dir, f))
    ]
    return sorted(files)


# ── Pipeline ──────────────────────────────────────────────────────────── #

class Pipeline:
    """
    Top-level orchestrator. Owns IndexCreator and MakeBinFile.

    Accepts file_slice and doc_id_offset (Phase 1 amendment for Phase 2
    compatibility). For Phase 1 single-pipeline execution:
    file_slice = all_files, doc_id_offset = 0.
    """

    def __init__(self, file_slice: list[str], doc_id_offset: int = 0) -> None:
        """
        Args:
            file_slice:    Subset of the sorted corpus file list for this pipeline.
            doc_id_offset: Starting doc ID for this pipeline's documents.
        """
        self._index_creator = IndexCreator(file_slice, doc_id_offset)
        self._make_bin_file = MakeBinFile()

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    def run(self, output_path: str) -> None:
        """
        Run the full pipeline: ingest documents → build index → write binary.

        Args:
            output_path: Destination path for the binary index file.
        """
        inverted_index: dict[str, list[int]] = self._index_creator.run()
        self._make_bin_file.write(inverted_index, output_path)


# ── Entry point ───────────────────────────────────────────────────────── #

def main() -> None:
    parser = argparse.ArgumentParser(description="Phase 1 Python Indexing Pipeline")
    parser.add_argument("--corpus", required=True, help="Path to corpus directory")
    parser.add_argument("--out", required=True, help="Output path for index.bin")
    args = parser.parse_args()

    if not os.path.isdir(args.corpus):
        print(f"Error: corpus directory '{args.corpus}' does not exist", file=sys.stderr)
        sys.exit(1)

    sorted_files: list[str] = presort_corpus(args.corpus)

    if not sorted_files:
        print(f"Error: no files found in corpus directory '{args.corpus}'", file=sys.stderr)
        sys.exit(1)

    print(f"Corpus: {len(sorted_files)} documents found in '{args.corpus}'")

    pipeline = Pipeline(file_slice=sorted_files, doc_id_offset=0)
    pipeline.run(output_path=args.out)

    print(f"Index written to '{args.out}'")


if __name__ == "__main__":
    main()
