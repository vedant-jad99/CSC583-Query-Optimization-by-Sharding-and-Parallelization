"""
shard_builder.py
────────────────
Phase 2 top-level orchestrator for sharded index construction.

Partitions the sorted corpus file list into N equal slices, computes
globally consistent doc ID offsets, and drives N Pipeline instances
in parallel via ProcessPoolExecutor (true multiprocessing — one OS
process per shard, each with its own GIL).

Output: shards/shard_0.bin ... shards/shard_{N-1}.bin

Design decisions:
  - N_SHARDS read from environment variable (default 4)
  - Doc ID offset per shard: offset_i = i × (total_docs // N_SHARDS)
    Guarantees globally unique doc IDs across all shards without
    any coordination between worker processes at runtime.
  - run_pipeline() is a module-level function (not a method) because
    ProcessPoolExecutor requires picklable callables. Lambdas and
    instance methods are not reliably picklable across processes.
  - Output directory created if it does not exist.

Usage:
    Called by main_sharded.py — not invoked directly.

Author: Vedant Keshav Jadhav
Phase:  2
"""

import os
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed

# Pipeline is in the same directory (scripts/pipeline/)
sys.path.insert(0, os.path.dirname(__file__))
from pipeline import Pipeline


def run_pipeline(file_slice: list[str],
                 offset: int,
                 shard_id: int,
                 output_dir: str) -> tuple[int, str]:
    """
    Build one shard index from a file slice and write it to disk.

    This is a module-level function so ProcessPoolExecutor can pickle it.
    Each call runs in a separate OS process with its own Python interpreter.

    Args:
        file_slice:  Ordered list of file paths for this shard.
        offset:      Starting doc ID for this shard.
        shard_id:    Shard index (0-based). Used to name the output file.
        output_dir:  Directory to write shard_{shard_id}.bin into.

    Returns:
        (shard_id, output_path) on success.

    Raises:
        Exception: Propagated back to the main process via the future.
    """
    output_path = os.path.join(output_dir, f"shard_{shard_id}.bin")
    pipeline = Pipeline(file_slice=file_slice, doc_id_offset=offset)
    pipeline.run(output_path=output_path)
    return shard_id, output_path



class ShardBuilder:
    """
    Orchestrates parallel sharded index construction.

    Reads N_SHARDS from the environment (default 4), partitions the
    sorted corpus file list, computes per-shard doc ID offsets, and
    launches N Pipeline instances in parallel via ProcessPoolExecutor.

    Usage:
        builder = ShardBuilder(sorted_files, output_dir="shards/")
        builder.build()
    """

    DEFAULT_N_SHARDS = 4

    def __init__(self,
                 sorted_files: list[str],
                 output_dir: str = "shards/") -> None:
        """
        Args:
            sorted_files: Pre-sorted list of all corpus file paths.
                          Must be sorted identically every run —
                          this is the invariant that guarantees globally
                          unique doc IDs across shards.
            output_dir:   Directory to write shard bin files into.
                          Created if it does not exist.
        """
        self._sorted_files = sorted_files
        self._output_dir   = output_dir
        self._n_shards     = self._read_n_shards()


    def build(self) -> list[str]:
        """
        Partition the corpus and build all N shards in parallel.

        Returns:
            List of output .bin file paths in shard order.

        Raises:
            RuntimeError: If any shard build fails.
        """
        os.makedirs(self._output_dir, exist_ok=True)

        total_docs   = len(self._sorted_files)
        shard_size   = total_docs // self._n_shards
        remainder    = total_docs  % self._n_shards

        print(f"ShardBuilder: {total_docs} documents → {self._n_shards} shards")
        print(f"  Base shard size: {shard_size} docs"
              f"  (last shard gets {shard_size + remainder} docs)")
        print(f"  Output dir: {self._output_dir}")

        # Build (file_slice, offset) pairs for each shard
        shard_assignments: list[tuple[list[str], int]] = []
        current_offset = 0
        for i in range(self._n_shards):
            # Last shard absorbs any remainder docs
            size = shard_size + (remainder if i == self._n_shards - 1 else 0)
            start = i * shard_size
            end   = start + size
            shard_assignments.append((self._sorted_files[start:end], current_offset))
            current_offset += size

        # Launch N processes in parallel
        output_paths: list[str] = [""] * self._n_shards

        with ProcessPoolExecutor(max_workers=self._n_shards) as executor:
            futures = {
                executor.submit(
                    run_pipeline,
                    file_slice,
                    offset,
                    shard_id,
                    self._output_dir,
                ): shard_id
                for shard_id, (file_slice, offset) in enumerate(shard_assignments)
            }

            for future in as_completed(futures):
                shard_id = futures[future]
                try:
                    sid, path = future.result()
                    output_paths[sid] = path
                    size_kb = os.path.getsize(path) / 1024
                    print(f"  ✓ shard_{sid}.bin  ({size_kb:.1f} KB)")
                except Exception as e:
                    raise RuntimeError(
                        f"Shard {shard_id} build failed: {e}"
                    ) from e

        print(f"ShardBuilder: all {self._n_shards} shards complete.")
        return output_paths


    @staticmethod
    def _read_n_shards() -> int:
        env = os.environ.get("N_SHARDS", "")
        if not env:
            return ShardBuilder.DEFAULT_N_SHARDS
        try:
            n = int(env)
            if n <= 0:
                raise ValueError
            return n
        except ValueError:
            print(f"Warning: invalid N_SHARDS='{env}', defaulting to "
                  f"{ShardBuilder.DEFAULT_N_SHARDS}", file=sys.stderr)
            return ShardBuilder.DEFAULT_N_SHARDS
