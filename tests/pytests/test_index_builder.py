import pytest
from index_builder import IndexBuilder


class TestIndexBuilderBasic:
    def test_single_doc_single_term(self):
        ib = IndexBuilder()
        ib.add_document(0, ["hello"])
        result = ib.build()
        assert result == {"hello": [0]}

    def test_single_doc_multiple_terms(self):
        ib = IndexBuilder()
        ib.add_document(0, ["hello", "world"])
        result = ib.build()
        assert result == {"hello": [0], "world": [0]}

    def test_multiple_docs_shared_term(self):
        ib = IndexBuilder()
        ib.add_document(0, ["hello"])
        ib.add_document(1, ["hello"])
        ib.add_document(2, ["hello"])
        result = ib.build()
        assert result == {"hello": [0, 1, 2]}

    def test_multiple_docs_different_terms(self):
        ib = IndexBuilder()
        ib.add_document(0, ["hello"])
        ib.add_document(1, ["world"])
        result = ib.build()
        assert result == {"hello": [0], "world": [1]}


class TestIndexBuilderDeduplication:
    def test_duplicate_term_in_same_doc(self):
        """Same term appearing multiple times in one doc produces ONE entry."""
        ib = IndexBuilder()
        ib.add_document(0, ["hello", "hello", "hello"])
        result = ib.build()
        assert result == {"hello": [0]}

    def test_duplicate_doc_ids_across_calls(self):
        """Adding same doc twice for same term still deduplicates."""
        ib = IndexBuilder()
        ib.add_document(0, ["hello"])
        ib.add_document(0, ["hello"])
        result = ib.build()
        assert result == {"hello": [0]}


class TestIndexBuilderSorting:
    def test_posting_lists_sorted(self):
        ib = IndexBuilder()
        ib.add_document(5, ["term"])
        ib.add_document(1, ["term"])
        ib.add_document(3, ["term"])
        ib.add_document(0, ["term"])
        result = ib.build()
        assert result["term"] == [0, 1, 3, 5]

    def test_out_of_order_insertion(self):
        ib = IndexBuilder()
        ib.add_document(100, ["x"])
        ib.add_document(2, ["x"])
        ib.add_document(50, ["x"])
        result = ib.build()
        assert result["x"] == [2, 50, 100]


class TestIndexBuilderEdge:
    def test_empty_build(self):
        ib = IndexBuilder()
        result = ib.build()
        assert result == {}

    def test_empty_token_list(self):
        ib = IndexBuilder()
        ib.add_document(0, [])
        result = ib.build()
        assert result == {}

    def test_large_number_of_documents(self):
        ib = IndexBuilder()
        for i in range(10000):
            ib.add_document(i, ["common"])
        result = ib.build()
        assert len(result["common"]) == 10000
        assert result["common"] == list(range(10000))

    def test_large_vocabulary(self):
        ib = IndexBuilder()
        for i in range(5000):
            ib.add_document(0, [f"term_{i}"])
        result = ib.build()
        assert len(result) == 5000

    def test_doc_id_with_offset(self):
        """Simulates Phase 2 shard with offset doc IDs."""
        ib = IndexBuilder()
        ib.add_document(25000, ["hello"])
        ib.add_document(25001, ["hello", "world"])
        ib.add_document(25002, ["world"])
        result = ib.build()
        assert result["hello"] == [25000, 25001]
        assert result["world"] == [25001, 25002]
