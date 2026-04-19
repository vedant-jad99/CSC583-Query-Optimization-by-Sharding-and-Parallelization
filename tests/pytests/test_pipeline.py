import os
import struct
import tempfile
import pytest
import importlib
import sys

# pipeline.py lives inside the pipeline/ package directory, which shadows it.
# Force-load the module file directly.
_spec = importlib.util.spec_from_file_location(
    "pipeline_module",
    os.path.join(os.path.dirname(__file__), "..", "..", "scripts", "pipeline", "pipeline.py"),
)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
Pipeline = _mod.Pipeline
presort_corpus = _mod.presort_corpus


_MAGIC = b"INVI_100"


def _write(path, text):
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def vbyte_decode_n(data: bytes, offset: int, n: int) -> tuple[list[int], int]:
    """Decode exactly `n` VByte-encoded values starting at `offset` in `data`."""
    values = []
    current = 0
    shift = 0
    pos = offset
    while len(values) < n and pos < len(data):
        byte = data[pos]
        pos += 1
        if byte & 0x80:
            current |= (byte & 0x7F) << shift
            values.append(current)
            current = 0
            shift = 0
        else:
            current |= (byte & 0x7F) << shift
            shift += 7
    return values, pos


def delta_expand(deltas: list[int]) -> list[int]:
    if not deltas:
        return []
    doc_ids = [deltas[0]]
    for i in range(1, len(deltas)):
        doc_ids.append(doc_ids[-1] + deltas[i])
    return doc_ids


def read_bin_file(path: str) -> dict[str, list[int]]:
    """Read the binary index format: magic(8) + num_terms(4) + entries + crc32(4)."""
    result = {}
    with open(path, "rb") as f:
        raw = f.read()

    assert raw[:8] == _MAGIC
    num_terms = struct.unpack_from("<I", raw, 8)[0]
    pos = 12

    for _ in range(num_terms):
        term_len = struct.unpack_from("<H", raw, pos)[0]
        pos += 2
        doc_count = struct.unpack_from("<I", raw, pos)[0]
        pos += 4
        term = raw[pos:pos + term_len].decode("utf-8")
        pos += term_len
        deltas, pos = vbyte_decode_n(raw, pos, doc_count)
        doc_ids = delta_expand(deltas)
        result[term] = doc_ids

    return result


# ── presort_corpus ────────────────────────────────────────────────────

class TestPresortCorpus:
    def test_alphabetical_order(self, tmp_path):
        for name in ["c.txt", "a.txt", "b.txt"]:
            (tmp_path / name).write_text("x")
        result = presort_corpus(str(tmp_path))
        names = [os.path.basename(p) for p in result]
        assert names == ["a.txt", "b.txt", "c.txt"]

    def test_deterministic(self, tmp_path):
        for name in ["z.txt", "m.txt", "a.txt", "q.txt"]:
            (tmp_path / name).write_text("x")
        r1 = presort_corpus(str(tmp_path))
        r2 = presort_corpus(str(tmp_path))
        assert r1 == r2

    def test_returns_full_paths(self, tmp_path):
        (tmp_path / "a.txt").write_text("x")
        result = presort_corpus(str(tmp_path))
        assert os.path.isabs(result[0])

    def test_ignores_directories(self, tmp_path):
        (tmp_path / "file.txt").write_text("x")
        (tmp_path / "subdir").mkdir()
        result = presort_corpus(str(tmp_path))
        assert len(result) == 1
        assert "file.txt" in result[0]

    def test_empty_directory(self, tmp_path):
        result = presort_corpus(str(tmp_path))
        assert result == []

    def test_numeric_filenames_sorted_lexicographically(self, tmp_path):
        for name in ["10.txt", "2.txt", "1.txt", "20.txt"]:
            (tmp_path / name).write_text("x")
        result = presort_corpus(str(tmp_path))
        names = [os.path.basename(p) for p in result]
        assert names == ["1.txt", "10.txt", "2.txt", "20.txt"]

    def test_mixed_extensions(self, tmp_path):
        for name in ["b.txt", "a.dat", "c.log"]:
            (tmp_path / name).write_text("x")
        result = presort_corpus(str(tmp_path))
        names = [os.path.basename(p) for p in result]
        assert names == ["a.dat", "b.txt", "c.log"]


# ── Pipeline end-to-end ───────────────────────────────────────────────

class TestPipelineEndToEnd:
    def test_single_doc(self, tmp_path):
        doc = tmp_path / "corpus" / "a.txt"
        doc.parent.mkdir()
        doc.write_text("Information retrieval systems")
        out = str(tmp_path / "index.bin")

        files = presort_corpus(str(tmp_path / "corpus"))
        Pipeline(file_slice=files, doc_id_offset=0).run(out)

        result = read_bin_file(out)
        assert "inform" in result
        assert "retriev" in result
        assert result["inform"] == [0]

    def test_multiple_docs(self, tmp_path):
        corpus = tmp_path / "corpus"
        corpus.mkdir()
        (corpus / "a.txt").write_text("information retrieval")
        (corpus / "b.txt").write_text("boolean retrieval model")
        (corpus / "c.txt").write_text("inverted index")
        out = str(tmp_path / "index.bin")

        files = presort_corpus(str(corpus))
        Pipeline(file_slice=files, doc_id_offset=0).run(out)

        result = read_bin_file(out)
        assert result["retriev"] == [0, 1]
        assert result["inform"] == [0]
        assert result["boolean"] == [1]
        assert result["invert"] == [2]
        assert result["index"] == [2]

    def test_output_file_created(self, tmp_path):
        corpus = tmp_path / "corpus"
        corpus.mkdir()
        (corpus / "a.txt").write_text("hello world")
        out = str(tmp_path / "index.bin")

        files = presort_corpus(str(corpus))
        Pipeline(file_slice=files, doc_id_offset=0).run(out)
        assert os.path.exists(out)
        assert os.path.getsize(out) > 0

    def test_valid_magic_header(self, tmp_path):
        corpus = tmp_path / "corpus"
        corpus.mkdir()
        (corpus / "a.txt").write_text("test")
        out = str(tmp_path / "index.bin")

        files = presort_corpus(str(corpus))
        Pipeline(file_slice=files, doc_id_offset=0).run(out)

        with open(out, "rb") as f:
            assert f.read(8) == _MAGIC


class TestPipelineOffset:
    def test_offset_applied(self, tmp_path):
        corpus = tmp_path / "corpus"
        corpus.mkdir()
        (corpus / "a.txt").write_text("hello")
        (corpus / "b.txt").write_text("hello")
        out = str(tmp_path / "index.bin")

        files = presort_corpus(str(corpus))
        Pipeline(file_slice=files, doc_id_offset=500).run(out)

        result = read_bin_file(out)
        assert result["hello"] == [500, 501]

    def test_shard_simulation(self, tmp_path):
        """Simulate Phase 2: two shards with non-overlapping doc ID ranges."""
        corpus = tmp_path / "corpus"
        corpus.mkdir()
        for i in range(6):
            (corpus / f"doc{i:02d}.txt").write_text("common term")

        files = presort_corpus(str(corpus))

        # Shard 0: first 3 files, offset 0
        out0 = str(tmp_path / "shard_0.bin")
        Pipeline(file_slice=files[:3], doc_id_offset=0).run(out0)

        # Shard 1: last 3 files, offset 3
        out1 = str(tmp_path / "shard_1.bin")
        Pipeline(file_slice=files[3:], doc_id_offset=3).run(out1)

        r0 = read_bin_file(out0)
        r1 = read_bin_file(out1)

        # No doc ID overlap between shards
        ids_0 = set(r0["common"])
        ids_1 = set(r1["common"])
        assert ids_0 == {0, 1, 2}
        assert ids_1 == {3, 4, 5}
        assert ids_0.isdisjoint(ids_1)


class TestPipelineEdge:
    def test_all_stop_words_doc(self, tmp_path):
        corpus = tmp_path / "corpus"
        corpus.mkdir()
        (corpus / "a.txt").write_text("the a is and or not")
        out = str(tmp_path / "index.bin")

        files = presort_corpus(str(corpus))
        Pipeline(file_slice=files, doc_id_offset=0).run(out)

        result = read_bin_file(out)
        assert result == {}

    def test_empty_file(self, tmp_path):
        corpus = tmp_path / "corpus"
        corpus.mkdir()
        (corpus / "a.txt").write_text("")
        out = str(tmp_path / "index.bin")

        files = presort_corpus(str(corpus))
        Pipeline(file_slice=files, doc_id_offset=0).run(out)

        result = read_bin_file(out)
        assert result == {}

    def test_large_corpus(self, tmp_path):
        corpus = tmp_path / "corpus"
        corpus.mkdir()
        for i in range(100):
            (corpus / f"doc_{i:04d}.txt").write_text(
                f"document number {i} about information retrieval and indexing"
            )
        out = str(tmp_path / "index.bin")

        files = presort_corpus(str(corpus))
        Pipeline(file_slice=files, doc_id_offset=0).run(out)

        result = read_bin_file(out)
        assert len(result["inform"]) == 100
        assert result["inform"] == list(range(100))

    def test_idempotent(self, tmp_path):
        """Running the pipeline twice on same input produces identical output."""
        corpus = tmp_path / "corpus"
        corpus.mkdir()
        (corpus / "a.txt").write_text("information retrieval")
        (corpus / "b.txt").write_text("boolean query model")

        files = presort_corpus(str(corpus))

        out1 = str(tmp_path / "run1.bin")
        out2 = str(tmp_path / "run2.bin")
        Pipeline(file_slice=files, doc_id_offset=0).run(out1)
        Pipeline(file_slice=files, doc_id_offset=0).run(out2)

        with open(out1, "rb") as f1, open(out2, "rb") as f2:
            assert f1.read() == f2.read()

    def test_pipeline_owns_subcomponents(self):
        p = Pipeline(file_slice=[], doc_id_offset=0)
        assert hasattr(p, "_index_creator")
        assert hasattr(p, "_make_bin_file")
