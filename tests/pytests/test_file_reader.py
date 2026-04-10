import os
import tempfile
import pytest
from file_reader import FileReader


@pytest.fixture
def corpus_dir():
    with tempfile.TemporaryDirectory() as d:
        yield d


def _write(path, text):
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


# ── Basic functionality ──────────────────────────────────────────────

class TestFileReaderBasic:
    def test_single_file(self, corpus_dir):
        p = os.path.join(corpus_dir, "a.txt")
        _write(p, "hello world")
        results = list(FileReader([p]).read())
        assert results == [(0, "hello world")]

    def test_multiple_files_sequential_ids(self, corpus_dir):
        paths = []
        for i, name in enumerate(["a.txt", "b.txt", "c.txt"]):
            p = os.path.join(corpus_dir, name)
            _write(p, f"doc {i}")
            paths.append(p)
        results = list(FileReader(paths).read())
        assert results == [(0, "doc 0"), (1, "doc 1"), (2, "doc 2")]

    def test_preserves_file_order(self, corpus_dir):
        p_z = os.path.join(corpus_dir, "z.txt")
        p_a = os.path.join(corpus_dir, "a.txt")
        _write(p_z, "last")
        _write(p_a, "first")
        results = list(FileReader([p_z, p_a]).read())
        assert results[0] == (0, "last")
        assert results[1] == (1, "first")


# ── Doc ID offset (Phase 1 amendment) ────────────────────────────────

class TestFileReaderOffset:
    def test_offset_zero(self, corpus_dir):
        p = os.path.join(corpus_dir, "a.txt")
        _write(p, "text")
        results = list(FileReader([p], doc_id_offset=0).read())
        assert results[0][0] == 0

    def test_offset_nonzero(self, corpus_dir):
        paths = []
        for name in ["a.txt", "b.txt", "c.txt"]:
            p = os.path.join(corpus_dir, name)
            _write(p, "x")
            paths.append(p)
        results = list(FileReader(paths, doc_id_offset=1000).read())
        assert [r[0] for r in results] == [1000, 1001, 1002]

    def test_offset_large(self, corpus_dir):
        p = os.path.join(corpus_dir, "a.txt")
        _write(p, "x")
        results = list(FileReader([p], doc_id_offset=99999).read())
        assert results[0][0] == 99999


# ── Edge cases ────────────────────────────────────────────────────────

class TestFileReaderEdge:
    def test_empty_file(self, corpus_dir):
        p = os.path.join(corpus_dir, "empty.txt")
        _write(p, "")
        results = list(FileReader([p]).read())
        assert results == [(0, "")]

    def test_empty_file_list(self):
        results = list(FileReader([]).read())
        assert results == []

    def test_unicode_content(self, corpus_dir):
        p = os.path.join(corpus_dir, "uni.txt")
        _write(p, "cafe\u0301 na\u00efve r\u00e9sum\u00e9 \u00fc\u00f1\u00ee")
        results = list(FileReader([p]).read())
        assert results[0][0] == 0
        assert "caf" in results[0][1]

    def test_multiline_content(self, corpus_dir):
        p = os.path.join(corpus_dir, "multi.txt")
        _write(p, "line one\nline two\nline three")
        results = list(FileReader([p]).read())
        assert results[0][1].count("\n") == 2

    def test_large_file(self, corpus_dir):
        p = os.path.join(corpus_dir, "big.txt")
        content = "word " * 100000
        _write(p, content)
        results = list(FileReader([p]).read())
        assert len(results[0][1]) == len(content)

    def test_nonexistent_file_raises(self):
        with pytest.raises(FileNotFoundError):
            list(FileReader(["/nonexistent/path.txt"]).read())

    def test_special_characters_in_filename(self, corpus_dir):
        p = os.path.join(corpus_dir, "file with spaces (1).txt")
        _write(p, "content")
        results = list(FileReader([p]).read())
        assert results == [(0, "content")]

    def test_generator_is_lazy(self, corpus_dir):
        p = os.path.join(corpus_dir, "a.txt")
        _write(p, "text")
        reader = FileReader([p])
        gen = reader.read()
        assert hasattr(gen, "__next__")
