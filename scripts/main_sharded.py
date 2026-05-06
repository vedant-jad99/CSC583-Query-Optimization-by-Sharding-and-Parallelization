"""
main_sharded.py
───────────────
Phase 2 entry point for the sharded indexing pipeline.

Reads the corpus directory, presortes files for globally consistent
doc ID assignment, then delegates to ShardBuilder which partitions
the corpus across N shards and builds them in parallel.

Usage:
    python3 scripts/main_sharded.py --corpus data/corpus --out-dir shards/

    N_SHARDS environment variable controls shard count (default: 4).

    N_SHARDS=8 python3 scripts/main_sharded.py --corpus data/corpus --out-dir shards/

Makefile integration (PHASE=2):
    $(PYTHON) scripts/main_sharded.py --corpus data/corpus --out-dir shards/

Author: Chinmay Mhatre
Phase:  2
"""

import argparse
import os
import sys
import time

# Ensure scripts/pipeline/ is on the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "pipeline"))

from pipeline import presort_corpus
from shard_builder import ShardBuilder


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Phase 2 sharded index builder"
    )
    p.add_argument(
        "--corpus",
        required=True,
        help="Path to corpus directory"
    )
    p.add_argument(
        "--out-dir",
        default="shards/",
        help="Output directory for shard .bin files (default: shards/)"
    )
    return p.parse_args()


def main() -> None:
    args = parse_args()

    # Validate corpus
    if not os.path.isdir(args.corpus):
        print(f"Error: corpus directory not found: {args.corpus}",
              file=sys.stderr)
        sys.exit(1)

    # Presort corpus files — produces deterministic, globally consistent
    # document ordering. This is the single invariant that guarantees
    # unique doc IDs across all shards.
    t0 = time.perf_counter()
    sorted_files = presort_corpus(args.corpus)
    t1 = time.perf_counter()

    if not sorted_files:
        print(f"Error: no files found in corpus: {args.corpus}",
              file=sys.stderr)
        sys.exit(1)

    print(f"Corpus: {len(sorted_files)} documents found in '{args.corpus}' "
          f"(sorted in {(t1-t0)*1000:.1f} ms)")

    # Build shards
    t0 = time.perf_counter()

    builder = ShardBuilder(
        sorted_files=sorted_files,
        output_dir=args.out_dir,
    )
    output_paths = builder.build()

    t1 = time.perf_counter()

    print(f"\nDone. {len(output_paths)} shards built in {t1-t0:.3f} s")
    for path in output_paths:
        size_kb = os.path.getsize(path) / 1024
        print(f"  {path}  ({size_kb:.1f} KB)")


if __name__ == "__main__":
    main()
