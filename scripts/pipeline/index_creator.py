"""
index_creator.py
────────────────
Orchestrates document ingestion through to index construction.

Owns all four processing stages and runs them in sequence for each document:
    FileReader  → raw (doc_id, text) stream
    Tokenizer   → split text into tokens
    Normalizer  → casefold, punct remove, stop word filter, stem
    IndexBuilder→ accumulate into inverted index

The final output is a dict[str, list[int]] inverted index with sorted,
deduplicated posting lists — ready to be passed to MakeBinFile for
binary serialization.

Ownership:
    Pipeline
    └── IndexCreator          ← this module
        ├── FileReader
        ├── Tokenizer
        ├── Normalizer
        │   ├── CaseFolder
        │   ├── PunctuationRemover
        │   ├── StopWordFilter
        │   └── Stemmer
        └── IndexBuilder

Author: Chinmay Mhatre
Phase:  1
"""

from file_reader import FileReader
from tokenizer import Tokenizer
from normalizer import Normalizer
from index_builder import IndexBuilder


class IndexCreator:
    """
    Document ingestion orchestrator.

    Usage (called by Pipeline):
        creator = IndexCreator(file_list, doc_id_offset)
        inverted_index = creator.run()
    """

    def __init__(self, file_list: list[str], doc_id_offset: int = 0) -> None:
        """
        Args:
            file_list:     Pre-sorted list of absolute file paths.
            doc_id_offset: Starting doc ID for this slice.
                           Phase 1 passes 0; Phase 2 passes shard offset.
        """
        self._file_reader = FileReader(file_list, doc_id_offset)
        self._tokenizer = Tokenizer()
        self._normalizer = Normalizer()
        self._index_builder = IndexBuilder()

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    def run(self) -> dict[str, list[int]]:
        """
        Read all documents, tokenize, normalize, and build the inverted index.

        Returns:
            Inverted index — term → sorted list of doc IDs.
            Ready to be passed to MakeBinFile.write().
        """
        for doc_id, raw_text in self._file_reader.read():
            tokens: list[str] = self._tokenizer.tokenize(raw_text)
            normalized: list[str] = self._normalizer.normalize(tokens)
            self._index_builder.add_document(doc_id, normalized)

        return self._index_builder.build()
