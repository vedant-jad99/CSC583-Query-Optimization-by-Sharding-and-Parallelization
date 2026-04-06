"""
file_reader.py
──────────────
Reads raw documents from disk and yields (doc_id, raw_text) pairs.

Assigns doc IDs as doc_id_offset + local_index where local_index is the
position of the document within the provided file list. This supports
Phase 2 sharding where each shard receives a different offset to ensure
globally unique doc IDs.

Ownership:
    IndexCreator
    └── FileReader          ← this module

Author: Chinmay Mhatre
Phase:  1
"""

import os
from typing import Iterator


class FileReader:
    """
    Reads raw document files and yields (doc_id, raw_text) pairs.

    The caller provides a pre-sorted file list and an optional doc ID offset.
    FileReader has no knowledge of sharding — it simply reads files and
    assigns IDs based on position + offset.
    """

    def __init__(self, file_list: list[str], doc_id_offset: int = 0) -> None:
        """
        Args:
            file_list:     Ordered list of absolute file paths to read.
                           Order determines doc ID assignment.
            doc_id_offset: Starting doc ID for this file slice.
                           Phase 1 passes 0; Phase 2 passes shard offset.
        """
        self._file_list: list[str] = file_list
        self._doc_id_offset: int = doc_id_offset

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    def read(self) -> Iterator[tuple[int, str]]:
        """
        Yield (doc_id, raw_text) for each file in the file list.

        Doc IDs are assigned as doc_id_offset + local_index.
        Files are read as UTF-8 plaintext.

        Yields:
            Tuple of (doc_id, raw_text) for each document.

        Raises:
            FileNotFoundError: If a file in the list does not exist.
        """
        for local_index, filepath in enumerate(self._file_list):
            doc_id: int = self._doc_id_offset + local_index
            with open(filepath, "r", encoding="utf-8") as f:
                raw_text: str = f.read()
            yield (doc_id, raw_text)
