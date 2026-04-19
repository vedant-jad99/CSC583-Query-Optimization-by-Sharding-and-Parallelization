"""
e2e_test.py
───────────
End-to-end test for Phase 1.

What this tests:
  TIER 1 — index.bin structural validation
      Reads the binary file manually and checks every header field,
      every per-term record, and the CRC32 checksum.

  TIER 2 — Index content checks
      Decodes the full index back into a Python dict and verifies
      properties that must hold for any correctly built index:
        - Posting lists are sorted and deduplicated
        - Terms are non-empty strings
        - Every doc ID is within the valid range [0, num_docs)

  TIER 3 — Corpus spot-checks
      Verifies that terms which must exist in a 224-page Wikipedia
      corpus are present in the index with plausible posting list sizes.
      Term forms match the Porter stemmer in preprocessor.cpp.

  TIER 4 — Boolean query correctness via C++ engine
      Launches run_engine in --bench mode (persistent process, stdin/stdout).
      Sends queries in POSTFIX notation — required by IR_System::processQuery()
      which uses a stack evaluator, not an infix parser.

      Query format examples:
          Single term:        "histori"
          AND (A ∩ B):        "term_a term_b AND"
          OR  (A ∪ B):        "term_a term_b OR"
          NOT (∁A):           "term_a NOT"

      Checks:
        - Single-term results match decoded index exactly
        - AND result == exact intersection of both operands
        - OR  result == exact union of both operands
        - NOT result is disjoint from positive term result
        - term ∪ NOT(term) == all doc IDs (complement check)

Usage:
    # Run from the project root (same directory as the Makefile)
    python3 tests/e2e_test.py

    # Skip Tier 4 if C++ binary is not yet built:
    python3 tests/e2e_test.py --skip-engine

Requirements:
    - index.bin must exist (run `make` first)
    - run_engine must exist (run `make` first) unless --skip-engine is passed
    - Python 3.9+, no third-party dependencies

Author: Vedant Keshav Jadhav
Phase:  1
"""

import argparse
import os
import struct
import subprocess
import sys
import zlib

# ── Paths (relative to project root) ──────────────────────────────────── #
INDEX_BIN  = "index.bin"
ENGINE_BIN = "./run_engine"
CORPUS_DIR = "data/corpus"

# Magic bytes written by BinWriter (must match bin_writer.py exactly)
MAGIC = b"INVI_100"

# ── ANSI colour helpers ────────────────────────────────────────────────── #
GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
RESET  = "\033[0m"

def ok(msg: str)   -> None: print(f"  {GREEN}PASS{RESET}  {msg}")
def fail(msg: str) -> None: print(f"  {RED}FAIL{RESET}  {msg}"); _failures.append(msg)
def info(msg: str) -> None: print(f"  {YELLOW}INFO{RESET}  {msg}")

_failures: list[str] = []


# ══════════════════════════════════════════════════════════════════════════ #
# TIER 1 — Binary format validation                                         #
# ══════════════════════════════════════════════════════════════════════════ #

def tier1_format_validation(data: bytes) -> dict[str, list[int]] | None:
    """
    Walk the raw bytes of index.bin and validate every field.
    Returns the decoded index (term → doc IDs) if valid, None on fatal error.
    """
    print("\n── Tier 1: Binary format validation ─────────────────────────────")
    pos = 0

    # ── Magic ──────────────────────────────────────────────────────────── #
    if len(data) < 8:
        fail("File is shorter than the magic header (< 8 bytes)")
        return None

    magic = data[pos:pos+8]; pos += 8
    if magic == MAGIC:
        ok(f"Magic bytes correct: {magic}")
    else:
        fail(f"Magic mismatch. Expected {MAGIC!r}, got {magic!r}")
        return None

    # ── Number of terms ────────────────────────────────────────────────── #
    if len(data) < pos + 4:
        fail("File truncated before num_terms field")
        return None

    num_terms: int = struct.unpack_from("<I", data, pos)[0]; pos += 4
    if num_terms > 0:
        ok(f"num_terms = {num_terms:,}")
    else:
        fail("num_terms is 0 — index appears empty")
        return None

    # ── Per-term records ───────────────────────────────────────────────── #
    index: dict[str, list[int]] = {}

    for i in range(num_terms):
        # term_len (uint16)
        if pos + 2 > len(data):
            fail(f"Truncated at term_len for term {i}")
            return None
        term_len: int = struct.unpack_from("<H", data, pos)[0]; pos += 2

        # doc_count (uint32)
        if pos + 4 > len(data):
            fail(f"Truncated at doc_count for term {i}")
            return None
        doc_count: int = struct.unpack_from("<I", data, pos)[0]; pos += 4

        # term string
        if pos + term_len > len(data):
            fail(f"Truncated at term string for term {i}")
            return None
        term: str = data[pos:pos+term_len].decode("utf-8"); pos += term_len

        # VByte decode — mirrors VBDecoder::decode() in decompressor.cpp exactly:
        #   value |= (byte & 0x7F) << shift
        #   if byte & 0x80 → final byte, abs_id = prev_id + value
        doc_ids: list[int] = []
        prev  = 0
        value = 0
        shift = 0
        decoded = 0

        while decoded < doc_count:
            if pos >= len(data):
                fail(f"Truncated inside VByte stream for term '{term}'")
                return None
            byte   = data[pos]; pos += 1
            value |= (byte & 0x7F) << shift
            shift += 7
            if byte & 0x80:
                abs_id = prev + value
                doc_ids.append(abs_id)
                prev  = abs_id
                value = 0
                shift = 0
                decoded += 1

        index[term] = doc_ids

    ok(f"All {num_terms:,} term records parsed without truncation")

    # ── CRC32 checksum ─────────────────────────────────────────────────── #
    if len(data) < pos + 4:
        fail("File truncated at CRC32 field")
        return index

    stored_crc:   int = struct.unpack_from("<I", data, pos)[0]
    computed_crc: int = zlib.crc32(data[:pos]) & 0xFFFF_FFFF

    if stored_crc == computed_crc:
        ok(f"CRC32 checksum valid: 0x{stored_crc:08X}")
    else:
        fail(f"CRC32 mismatch — stored 0x{stored_crc:08X}, computed 0x{computed_crc:08X}. "
             f"File may be corrupt.")

    return index


# ══════════════════════════════════════════════════════════════════════════ #
# TIER 2 — Index content correctness                                        #
# ══════════════════════════════════════════════════════════════════════════ #

def tier2_content_checks(index: dict[str, list[int]]) -> int:
    """
    Verify structural properties of the decoded index.
    Returns the number of unique doc IDs found.
    """
    print("\n── Tier 2: Index content correctness ────────────────────────────")

    all_doc_ids: set[int] = set()
    for doc_ids in index.values():
        all_doc_ids.update(doc_ids)
    num_docs = len(all_doc_ids)
    info(f"Unique doc IDs in index: {num_docs}  (= number of indexed documents)")

    corpus_files = [
        f for f in os.listdir(CORPUS_DIR)
        if os.path.isfile(os.path.join(CORPUS_DIR, f))
    ]
    info(f"Files in corpus directory: {len(corpus_files)}")

    if num_docs == len(corpus_files):
        ok("Doc ID count matches corpus file count")
    else:
        fail(f"Doc ID count ({num_docs}) != corpus file count ({len(corpus_files)})")

    unsorted = [t for t, ids in index.items() if ids != sorted(ids)]
    if not unsorted:
        ok("All posting lists are sorted ascending")
    else:
        fail(f"{len(unsorted)} posting lists are NOT sorted: {unsorted[:5]}")

    with_dupes = [t for t, ids in index.items() if len(ids) != len(set(ids))]
    if not with_dupes:
        ok("No duplicate doc IDs in any posting list")
    else:
        fail(f"{len(with_dupes)} posting lists contain duplicate doc IDs: {with_dupes[:5]}")

    negative = [t for t, ids in index.items() if any(d < 0 for d in ids)]
    if not negative:
        ok("All doc IDs are non-negative")
    else:
        fail(f"Negative doc IDs found in: {negative[:5]}")

    out_of_range = [t for t, ids in index.items() if any(d >= num_docs for d in ids)]
    if not out_of_range:
        ok(f"All doc IDs within valid range [0, {num_docs})")
    else:
        fail(f"Out-of-range doc IDs found in: {out_of_range[:5]}")

    empty_terms = [t for t in index if len(t.strip()) == 0]
    if not empty_terms:
        ok("No empty term strings")
    else:
        fail(f"{len(empty_terms)} empty term strings found")

    # Stop words defined in preprocessor.cpp STOP_WORDS — none should be indexed
    stop_words = {"the", "a", "an", "is", "in", "of", "and", "to", "it", "for"}
    found_stops = stop_words.intersection(index.keys())
    if not found_stops:
        ok("No common stop words present (stop word filter working)")
    else:
        fail(f"Stop words found in index (should have been filtered): {found_stops}")

    lengths = sorted(len(ids) for ids in index.values())
    info(f"Vocabulary size: {len(index):,} terms")
    info(f"Posting list lengths — "
         f"min: {lengths[0]}, "
         f"median: {lengths[len(lengths)//2]}, "
         f"max: {lengths[-1]}, "
         f"mean: {sum(lengths)/len(lengths):.1f}")

    return num_docs


# ══════════════════════════════════════════════════════════════════════════ #
# TIER 3 — Corpus spot-checks                                               #
# ══════════════════════════════════════════════════════════════════════════ #

def tier3_spot_checks(index: dict[str, list[int]], num_docs: int) -> None:
    """
    Check that specific stemmed terms exist in a 224-page Wikipedia corpus.
    Stemmed forms verified against the Porter stemmer in preprocessor.cpp.
    """
    print("\n── Tier 3: Corpus spot-checks ───────────────────────────────────")

    # (stemmed_term, min_docs, description)
    expected_terms = [
        ("wikipedia",  1,  "'wikipedia' — no stemming change"),
        ("histori",    2,  "'history' → Porter stem 'histori'"),
        ("refer",      2,  "'reference/referred' → 'refer'"),
        ("univers",    2,  "'university/universal' → 'univers'"),
        ("use",        5,  "'used/uses' → 'use' — very common"),
        ("govern",     2,  "'government' → 'govern'"),
        ("year",       2,  "'year/years' → 'year'"),
        ("world",      2,  "'world' → 'world'"),
        ("war",        1,  "'war' → 'war'"),
        ("countri",    1,  "'country' → 'countri'"),
    ]

    for term, min_docs, description in expected_terms:
        if term in index:
            n = len(index[term])
            if n >= min_docs:
                ok(f"'{term}' found in {n} docs  ({description})")
            else:
                fail(f"'{term}' found but only in {n} doc(s), expected >= {min_docs}  ({description})")
        else:
            fail(f"'{term}' not found in index  ({description}) — "
                 f"check stemmer consistency between Python Normalizer and C++ Preprocessor")

    rare     = [t for t, ids in index.items() if len(ids) <= 3]
    rare_pct = 100 * len(rare) / len(index)
    if rare_pct >= 50:
        ok(f"{rare_pct:.0f}% of terms appear in ≤3 docs (Zipfian distribution — expected)")
    else:
        fail(f"Only {rare_pct:.0f}% of terms appear in ≤3 docs — "
             f"distribution looks wrong, possible indexing issue")

    high_freq = [t for t, ids in index.items() if len(ids) > num_docs // 2]
    info(f"Terms appearing in >50% of docs: {len(high_freq)}")


# ══════════════════════════════════════════════════════════════════════════ #
# TIER 4 — C++ engine Boolean query correctness                             #
# ══════════════════════════════════════════════════════════════════════════ #

class EngineProcess:
    """
    Wraps run_engine in --bench mode as a persistent subprocess.

    Protocol (from main.cpp run_bench()):
      - Launch:  ./run_engine index.bin --bench
      - Engine prints "READY\\n" when initialised
      - Send query line → engine replies with space-separated doc IDs on one line
      - Send "EXIT\\n"   → engine exits cleanly

    Query format: POSTFIX — required by IR_System::processQuery() stack evaluator.
      The stack evaluator pushes posting lists for terms and applies operators
      when encountered. Infix order hits the operator before the second operand
      is on the stack, causing a runtime error.

      Single term:   "histori"
      AND:           "term_a term_b AND"
      OR:            "term_a term_b OR"
      NOT:           "term_a NOT"
    """

    def __init__(self, bin_path: str, index_path: str) -> None:
        self._proc = subprocess.Popen(
            [bin_path, index_path, "--bench"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        ready = self._proc.stdout.readline().strip()
        if ready != "READY":
            raise RuntimeError(f"Engine did not print READY, got: '{ready}'")

    def query(self, postfix_query: str) -> list[int] | None:
        try:
            self._proc.stdin.write(postfix_query + "\n")
            self._proc.stdin.flush()
            line = self._proc.stdout.readline().strip()
            if not line:
                return []
            return sorted(int(x) for x in line.split() if x.isdigit())
        except Exception as e:
            fail(f"Engine communication error on query '{postfix_query}': {e}")
            return None

    def close(self) -> None:
        try:
            self._proc.stdin.write("EXIT\n")
            self._proc.stdin.flush()
            self._proc.wait(timeout=5)
        except Exception:
            self._proc.kill()


def tier4_engine_queries(index: dict[str, list[int]]) -> None:
    print("\n── Tier 4: C++ engine Boolean query correctness ─────────────────")

    try:
        engine = EngineProcess(ENGINE_BIN, INDEX_BIN)
    except FileNotFoundError:
        fail(f"Engine binary not found at '{ENGINE_BIN}'. Run `make` first.")
        return
    except RuntimeError as e:
        fail(str(e))
        return

    info("Engine launched in --bench mode")

    # Pick two terms with moderate posting list sizes for interesting AND results
    candidates = sorted(
        [(t, len(ids)) for t, ids in index.items() if 3 <= len(ids) <= 20],
        key=lambda x: x[1],
        reverse=True,
    )

    if len(candidates) < 2:
        info("Not enough mid-frequency terms found. Skipping relational checks.")
        engine.close()
        return

    term_a, count_a = candidates[0]
    term_b, count_b = candidates[1]
    info(f"Selected terms: '{term_a}' ({count_a} docs), '{term_b}' ({count_b} docs)")

    # ── Single-term queries ──────────────────────────────────────────────── #
    res_a = engine.query(term_a)
    res_b = engine.query(term_b)

    if res_a is None or res_b is None:
        info("Single-term queries failed — skipping relational checks")
        engine.close()
        return

    expected_a = sorted(index[term_a])
    expected_b = sorted(index[term_b])

    if res_a == expected_a:
        ok(f"Single-term '{term_a}': engine matches decoded index ({len(res_a)} docs)")
    else:
        fail(f"Single-term '{term_a}': engine returned {res_a}, expected {expected_a}")

    if res_b == expected_b:
        ok(f"Single-term '{term_b}': engine matches decoded index ({len(res_b)} docs)")
    else:
        fail(f"Single-term '{term_b}': engine returned {res_b}, expected {expected_b}")

    # ── AND — postfix: "term_a term_b AND" ──────────────────────────────── #
    res_and = engine.query(f"{term_a} {term_b} AND")
    if res_and is not None:
        expected_and = sorted(set(res_a) & set(res_b))
        if res_and == expected_and:
            ok(f"AND query correct: {len(res_and)} docs "
               f"(intersection of {len(res_a)} ∩ {len(res_b)})")
        else:
            fail(f"AND query wrong.\n"
                 f"    Got:      {res_and}\n"
                 f"    Expected: {expected_and}")

        if set(res_and).issubset(set(res_a)) and set(res_and).issubset(set(res_b)):
            ok("AND result is a subset of both operand results")
        else:
            fail("AND result contains doc IDs not in one of the operands")

    # ── OR — postfix: "term_a term_b OR" ────────────────────────────────── #
    res_or = engine.query(f"{term_a} {term_b} OR")
    if res_or is not None:
        expected_or = sorted(set(res_a) | set(res_b))
        if res_or == expected_or:
            ok(f"OR query correct: {len(res_or)} docs "
               f"(union of {len(res_a)} ∪ {len(res_b)})")
        else:
            fail(f"OR query wrong.\n"
                 f"    Got:      {res_or}\n"
                 f"    Expected: {expected_or}")

        if set(res_a).issubset(set(res_or)) and set(res_b).issubset(set(res_or)):
            ok("OR result is a superset of both operand results")
        else:
            fail("OR result is missing doc IDs from one of the operands")

    # ── NOT — postfix: "term_a NOT" ─────────────────────────────────────── #
    res_not = engine.query(f"{term_a} NOT")
    if res_not is not None:
        if set(res_not).isdisjoint(set(res_a)):
            ok(f"NOT query: result is disjoint from '{term_a}' result")
        else:
            overlap = set(res_not) & set(res_a)
            fail(f"NOT result overlaps with '{term_a}' result: {sorted(overlap)}")

        # Complement check: term_a ∪ NOT(term_a) must equal all doc IDs
        all_doc_ids: set[int] = set()
        for ids in index.values():
            all_doc_ids.update(ids)

        complement = set(res_a) | set(res_not)
        if complement == all_doc_ids:
            ok(f"Complement check: '{term_a}' ∪ NOT('{term_a}') == "
               f"all {len(all_doc_ids)} doc IDs")
        else:
            missing = all_doc_ids - complement
            extra   = complement - all_doc_ids
            fail(f"Complement check failed.\n"
                 f"    Missing from union: {sorted(missing)[:10]}\n"
                 f"    Extra in union:     {sorted(extra)[:10]}")

    engine.close()
    info("Engine process closed cleanly")


# ══════════════════════════════════════════════════════════════════════════ #
# Main                                                                      #
# ══════════════════════════════════════════════════════════════════════════ #

def main() -> None:
    parser = argparse.ArgumentParser(description="Phase 1 end-to-end test")
    parser.add_argument(
        "--skip-engine",
        action="store_true",
        help="Skip Tier 4 (C++ engine queries). Use if binary not yet built."
    )
    args = parser.parse_args()

    print("=" * 60)
    print("  Phase 1 — End-to-End Test")
    print("=" * 60)

    if not os.path.isfile(INDEX_BIN):
        print(f"\n{RED}ERROR:{RESET} '{INDEX_BIN}' not found. Run `make` first.\n")
        sys.exit(1)
    if not os.path.isdir(CORPUS_DIR):
        print(f"\n{RED}ERROR:{RESET} corpus directory '{CORPUS_DIR}' not found.\n")
        sys.exit(1)

    with open(INDEX_BIN, "rb") as f:
        data = f.read()
    info(f"index.bin size: {len(data)/1024:.1f} KB")

    index = tier1_format_validation(data)
    if index is None:
        print(f"\n{RED}Tier 1 failed fatally — cannot continue.{RESET}\n")
        sys.exit(1)

    num_docs = tier2_content_checks(index)
    tier3_spot_checks(index, num_docs)

    if not args.skip_engine:
        tier4_engine_queries(index)
    else:
        print("\n── Tier 4: Skipped (--skip-engine) ──────────────────────────────")

    print("\n" + "=" * 60)
    if not _failures:
        print(f"  {GREEN}ALL CHECKS PASSED{RESET}")
    else:
        print(f"  {RED}{len(_failures)} CHECK(S) FAILED:{RESET}")
        for f in _failures:
            print(f"    • {f}")
    print("=" * 60 + "\n")

    sys.exit(0 if not _failures else 1)


if __name__ == "__main__":
    main()
