import os
import tempfile
import pytest
from index_creator import IndexCreator


def _write(path, text):
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


@pytest.fixture
def corpus_dir():
    with tempfile.TemporaryDirectory() as d:
        yield d


class TestIndexCreatorBasic:
    def test_single_doc(self, corpus_dir):
        p = os.path.join(corpus_dir, "a.txt")
        _write(p, "Information retrieval systems")
        ic = IndexCreator([p])
        result = ic.run()
        assert "inform" in result
        assert "retriev" in result
        assert "system" in result
        assert result["inform"] == [0]

    def test_multiple_docs_shared_terms(self, corpus_dir):
        p1 = os.path.join(corpus_dir, "a.txt")
        p2 = os.path.join(corpus_dir, "b.txt")
        _write(p1, "information retrieval")
        _write(p2, "information extraction")
        ic = IndexCreator([p1, p2])
        result = ic.run()
        assert result["inform"] == [0, 1]
        assert result["retriev"] == [0]
        assert result["extract"] == [1]

    def test_stop_words_removed(self, corpus_dir):
        p = os.path.join(corpus_dir, "a.txt")
        _write(p, "the quick brown fox is a very fast animal")
        ic = IndexCreator([p])
        result = ic.run()
        assert "the" not in result
        assert "is" not in result
        assert "a" not in result
        assert "quick" in result

    def test_case_insensitive(self, corpus_dir):
        p1 = os.path.join(corpus_dir, "a.txt")
        p2 = os.path.join(corpus_dir, "b.txt")
        _write(p1, "Information RETRIEVAL")
        _write(p2, "information retrieval")
        ic = IndexCreator([p1, p2])
        result = ic.run()
        assert result["inform"] == [0, 1]
        assert result["retriev"] == [0, 1]

    def test_stemming_applied(self, corpus_dir):
        p = os.path.join(corpus_dir, "a.txt")
        _write(p, "running computed searching")
        ic = IndexCreator([p])
        result = ic.run()
        assert "run" in result
        assert "comput" in result
        assert "search" in result
        assert "running" not in result


class TestIndexCreatorOffset:
    def test_offset_zero(self, corpus_dir):
        p = os.path.join(corpus_dir, "a.txt")
        _write(p, "hello")
        ic = IndexCreator([p], doc_id_offset=0)
        result = ic.run()
        assert result["hello"] == [0]

    def test_offset_nonzero(self, corpus_dir):
        p = os.path.join(corpus_dir, "a.txt")
        _write(p, "hello")
        ic = IndexCreator([p], doc_id_offset=5000)
        result = ic.run()
        assert result["hello"] == [5000]

    def test_offset_multiple_docs(self, corpus_dir):
        p1 = os.path.join(corpus_dir, "a.txt")
        p2 = os.path.join(corpus_dir, "b.txt")
        _write(p1, "shared")
        _write(p2, "shared")
        ic = IndexCreator([p1, p2], doc_id_offset=100)
        result = ic.run()
        assert result["share"] == [100, 101]


class TestIndexCreatorEdge:
    def test_empty_file(self, corpus_dir):
        p = os.path.join(corpus_dir, "empty.txt")
        _write(p, "")
        ic = IndexCreator([p])
        result = ic.run()
        assert result == {}

    def test_file_with_only_stop_words(self, corpus_dir):
        p = os.path.join(corpus_dir, "stops.txt")
        _write(p, "the a is and or not but if in on")
        ic = IndexCreator([p])
        result = ic.run()
        assert result == {}

    def test_file_with_only_punctuation(self, corpus_dir):
        p = os.path.join(corpus_dir, "punct.txt")
        _write(p, "!!! ... --- ??? ///")
        ic = IndexCreator([p])
        result = ic.run()
        assert result == {}

    def test_duplicate_words_deduplicated(self, corpus_dir):
        p = os.path.join(corpus_dir, "a.txt")
        _write(p, "hello hello hello hello hello")
        ic = IndexCreator([p])
        result = ic.run()
        assert result["hello"] == [0]

    def test_posting_lists_sorted(self, corpus_dir):
        """Even if files are processed out of ID order, posting lists are sorted."""
        paths = []
        for i in range(10):
            p = os.path.join(corpus_dir, f"doc_{i:02d}.txt")
            _write(p, "common term")
            paths.append(p)
        ic = IndexCreator(paths)
        result = ic.run()
        assert result["common"] == list(range(10))

    def test_owns_all_subcomponents(self):
        """IndexCreator must own FileReader, Tokenizer, Normalizer, IndexBuilder."""
        ic = IndexCreator([], 0)
        assert hasattr(ic, "_file_reader")
        assert hasattr(ic, "_tokenizer")
        assert hasattr(ic, "_normalizer")
        assert hasattr(ic, "_index_builder")
