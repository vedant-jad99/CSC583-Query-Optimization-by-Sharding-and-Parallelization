"""
make_bin_file.py
────────────────
Top-level serialization orchestrator. Receives the in-memory inverted index
from IndexCreator (via Pipeline) and produces the binary `index.bin` artifact
consumed by the C++ query engine at startup.

Ownership:
    MakeBinFile
    └── BinWriter
        └── VBEncoder          (used internally by BinWriter)

The index is sorted by term before writing. This is not required for
correctness (the C++ Decompressor builds a hash map, so order doesn't matter
for lookups), but it makes the output deterministic across runs — useful for
checksumming, debugging, and binary diffing during development.

Author: Vedant Keshav Jadhav
Phase:  1
"""

from bin_writer import BinWriter


class MakeBinFile:
    """
    Serialization orchestrator.

    Usage (called by Pipeline):
        maker = MakeBinFile()
        maker.write(inverted_index, "index.bin")
    """

    def __init__(self) -> None:
        self._writer = BinWriter()

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    def write(self, index: dict[str, list[int]], output_path: str) -> None:
        """
        Sort the index by term and write it to `output_path` as a binary file.

        Args:
            index:       Inverted index — term → sorted list of doc IDs.
                         Received from IndexCreator. Posting lists are assumed
                         sorted and deduplicated.
            output_path: Destination path for the binary file (e.g. "index.bin").
        """
        # Sort terms for deterministic, reproducible output.
        sorted_index: dict[str, list[int]] = dict(sorted(index.items()))

        self._writer.write(sorted_index, output_path)
