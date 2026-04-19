"""
vb_encoder.py
─────────────
Encodes a sorted posting list into a compact byte sequence using two stages:

  Stage 1 — Delta encoding:
      Transform absolute doc IDs into gaps (differences) between consecutive IDs.
      Gaps are always small integers even when doc IDs are large, which makes
      the subsequent variable-length encoding far more efficient.

      Example:
          Original:  [5, 8, 14, 100]
          Deltas:    [5, 3,  6,  86]   (first delta is id - 0 = id itself)

  Stage 2 — VByte encoding:
      Encode each delta using as few bytes as possible.
      Each byte contributes 7 bits of data. The high bit (bit 7) is a
      continuation flag:
          0 → more bytes follow for this value
          1 → this is the LAST byte for this value

      Example:  encode(300)
          300 in binary = 0b100101100
          Split into 7-bit groups from LSB: 0101100  (44),  10  (2)
          First byte:  44 | 0x00 = 0x2C  (continuation bit = 0, more follows)
          Second byte:  2 | 0x80 = 0x82  (continuation bit = 1, final byte)
          Result: [0x2C, 0x82]

      Single-byte range (0–127):  1 byte
      Two-byte range   (128–16383):  2 bytes
      For typical small gaps in a dense posting list, most values fit in 1–2 bytes.

Author: Vedant Keshav Jadhav
Phase:  1
"""


class VBEncoder:
    """
    Stateless encoder. All methods are static — instantiate or call on class directly.
    """

    @staticmethod
    def encode(posting_list: list[int]) -> bytes:
        """
        Delta-encode then VByte-encode a sorted posting list.

        Args:
            posting_list: Sorted list of non-negative integer doc IDs.
                          Must already be sorted (ascending). Duplicates are
                          not expected — IndexBuilder guarantees deduplication.

        Returns:
            bytes: Compact binary representation of the posting list.
                   The decoder must know the doc count (N) externally;
                   it is NOT embedded in the output of this method.
                   BinWriter stores N in the per-term header.
        """
        if not posting_list:
            return b""

        buf = bytearray()
        prev = 0

        for doc_id in posting_list:
            delta = doc_id - prev          # gap from previous (or from 0 for first)
            prev = doc_id
            VBEncoder._vbyte_encode(delta, buf)

        return bytes(buf)

    # ------------------------------------------------------------------ #
    # Internal helpers                                                     #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _vbyte_encode(value: int, buf: bytearray) -> None:
        """
        Append the VByte encoding of `value` to `buf` in-place.

        Encoding rule (from spec):
            while value > 127:
                emit (value & 0x7F)   # lower 7 bits, continuation bit = 0
                value >>= 7
            emit (value | 0x80)       # final byte, continuation bit = 1

        The loop emits bytes from least-significant 7-bit group to
        most-significant; the decoder reconstructs by shifting each
        7-bit group back into place.

        Args:
            value: Non-negative integer to encode. A gap of 0 is valid
                   (duplicate-adjacent doc IDs, though IndexBuilder removes them).
            buf:   Bytearray to append encoded bytes to.
        """
        if value < 0:
            raise ValueError(f"VByte encoding requires non-negative integers, got {value}")

        while value > 127:
            buf.append(value & 0x7F)   # emit low 7 bits; bit 7 = 0 (continue)
            value >>= 7

        buf.append(value | 0x80)       # emit final 7 bits; bit 7 = 1 (stop)
