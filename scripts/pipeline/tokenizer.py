"""
tokenizer.py
────────────
Splits raw text into tokens on whitespace and punctuation boundaries.

Uses a regex to extract contiguous sequences of alphanumeric characters.
All punctuation, whitespace, and special characters act as delimiters
and are discarded.

Ownership:
    IndexCreator
    └── Tokenizer          ← this module

Author: Chinmay Mhatre
Phase:  1
"""

import re


class Tokenizer:
    """
    Stateless tokenizer. Splits raw text into alphanumeric token strings.
    """

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    def tokenize(self, text: str) -> list[str]:
        """
        Split raw text into tokens.

        Args:
            text: Raw document text (may contain any characters).

        Returns:
            List of token strings. Each token is a contiguous run of
            [a-zA-Z0-9] characters. Empty input returns an empty list.
        """
        return re.findall(r"[a-zA-Z0-9]+", text)
