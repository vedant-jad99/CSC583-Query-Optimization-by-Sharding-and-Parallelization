"""
bin_writer.py
─────────────
Serializes the in-memory inverted index to the binary `index.bin` format
consumed by the C++ Decompressor at query time.

Binary format (little-endian throughout):
─────────────────────────────────────────────────────────────────────────
 Offset  Size    Field
─────────────────────────────────────────────────────────────────────────
 0       8 B     Magic + version:  b"INVI_\\x01\\x00\\x00"
 8       4 B     Number of terms   (uint32 LE)
 ── repeated for every term ──────────────────────────────────────────────
         2 B     Term length M     (uint16 LE)
         4 B     Doc ID count N    (uint32 LE)
         M B     Term string       (UTF-8, no null terminator)
         ? B     VByte-encoded delta doc IDs  (variable length)
 ─────────────────────────────────────────────────────────────────────────
 end-4   4 B     CRC32 checksum    (uint32 LE)  covers all bytes before it
─────────────────────────────────────────────────────────────────────────

Design notes:
  - The C++ Decompressor reads N (doc count) from the header to know when
    to stop VByte-decoding. The VByte bytes for a term are NOT length-prefixed;
    N controls the decode loop.
  - Term order in the file matches iteration order of the dict passed in.
    For reproducible files (helpful for debugging / checksumming), sort the
    index before passing it to write(). MakeBinFile does this.
  - The CRC32 covers the entire file body (magic through last term's bytes).
    The C++ side may verify it on load; a mismatch should abort with an error.

Author: Vedant Keshav Jadhav
Phase:  1
"""

import struct
import zlib

from vb_encoder import VBEncoder


# 8-byte magic: 5 ASCII chars + 3-byte version tag (major=1, minor=0, patch=0)
_MAGIC: bytes = b"INVI_\x01\x00\x00"


class BinWriter:
    """
    Writes the binary index file.
    Owns a VBEncoder for compressing posting lists.
    """

    def __init__(self) -> None:
        self._encoder = VBEncoder()

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    def write(self, index: dict[str, list[int]], output_path: str) -> None:
        """
        Serialize `index` and write it to `output_path`.

        Args:
            index:       Inverted index — term → sorted list of doc IDs.
                         Posting lists must already be sorted and deduplicated
                         (guaranteed by IndexBuilder).
            output_path: Destination file path, e.g. "index.bin".

        Raises:
            ValueError: If a term string is longer than 65535 bytes (uint16 max),
                        or a posting list has more than 4294967295 entries (uint32 max).
            OSError:    If the output file cannot be written.
        """
        buf = bytearray()

        # ── Header ────────────────────────────────────────────────────── #
        buf += _MAGIC                                   # 8 bytes
        buf += struct.pack("<I", len(index))            # num_terms: uint32 LE

        # ── Per-term records ──────────────────────────────────────────── #
        for term, posting_list in index.items():
            term_bytes: bytes = term.encode("utf-8")
            m: int = len(term_bytes)
            n: int = len(posting_list)

            if m > 0xFFFF:
                raise ValueError(
                    f"Term '{term[:40]}...' encodes to {m} bytes, "
                    f"exceeding uint16 max (65535)."
                )
            if n > 0xFFFF_FFFF:
                raise ValueError(
                    f"Posting list for '{term}' has {n} entries, "
                    f"exceeding uint32 max."
                )

            vbytes: bytes = VBEncoder.encode(posting_list)

            buf += struct.pack("<H", m)      # term_len:  uint16 LE
            buf += struct.pack("<I", n)      # doc_count: uint32 LE
            buf += term_bytes               # term string (no null terminator)
            buf += vbytes                   # VByte-encoded delta doc IDs

        # ── CRC32 checksum ────────────────────────────────────────────── #
        # zlib.crc32 returns a signed int on some Python versions;
        # mask to uint32 for safe packing.
        checksum: int = zlib.crc32(buf) & 0xFFFF_FFFF
        buf += struct.pack("<I", checksum)  # uint32 LE

        # ── Write to disk ─────────────────────────────────────────────── #
        with open(output_path, "wb") as f:
            f.write(buf)
