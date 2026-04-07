"""
index_builder.py
────────────────
Builds the in-memory inverted index from a stream of (doc_id, tokens) pairs.

Output is dict[str, list[int]] — term → sorted list of doc IDs.
Posting lists are deduplicated (a term appearing 5 times in doc 3 produces
only one entry for doc 3) and sorted in ascending order (required for
delta encoding in VBEncoder downstream).

Ownership:
    IndexCreator
    └── IndexBuilder          ← this module

Author: Chinmay Mhatre
Phase:  1
"""

from collections import defaultdict


class IndexBuilder:
    """
    Accumulates (doc_id, token_list) pairs and produces a finalized
    inverted index with sorted, deduplicated posting lists.
    """

    def __init__(self) -> None:
        self._index: dict[str, set[int]] = defaultdict(set)

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    def add_document(self, doc_id: int, tokens: list[str]) -> None:
        """
        Add all tokens from a single document to the index.

        Args:
            doc_id: Integer document ID (globally unique across shards).
            tokens: Normalized token list from Normalizer. Duplicates within
                    the same document are handled (set-based deduplication).
        """
        for token in tokens:
            self._index[token].add(doc_id)

    def build(self) -> dict[str, list[int]]:
        """
        Finalize and return the inverted index.

        Returns:
            dict mapping each term to a sorted list of doc IDs.
            Posting lists are guaranteed sorted (ascending) and deduplicated.
        """
        return {term: sorted(doc_ids) for term, doc_ids in self._index.items()}
