"""
normalizer.py
─────────────
Orchestrates the full text normalization pipeline applied to token lists.

Pipeline order (must be maintained — order affects output):
    CaseFold → PunctuationRemove → StopWordFilter → Stem

Each stage is a separate class for clean testing and benchmarking.
The Normalizer class owns all four and runs them in sequence.

The Stemmer uses NLTK's PorterStemmer. This MUST produce identical stems
to the C++ Preprocessor at query time — both sides use Porter's algorithm.

Ownership:
    IndexCreator
    └── Normalizer          ← this module
        ├── CaseFolder
        ├── PunctuationRemover
        ├── StopWordFilter
        └── Stemmer

Author: Chinmay Mhatre
Phase:  1
"""

import re
from nltk.stem import PorterStemmer as NLTKPorterStemmer


# ── Stop word set ─────────────────────────────────────────────────────── #
# Hardcoded for Phase 1. Static, no external file dependency.
# Must cover standard English function words to prevent enormous
# posting lists for high-frequency terms like "the", "is", "and".

STOP_WORDS: frozenset[str] = frozenset({
    "a", "an", "and", "are", "as", "at", "be", "but", "by", "for",
    "if", "in", "into", "is", "it", "no", "not", "of", "on", "or",
    "such", "that", "the", "their", "then", "there", "these", "they",
    "this", "to", "was", "will", "with", "about", "above", "after",
    "again", "all", "am", "any", "because", "been", "before", "being",
    "below", "between", "both", "can", "could", "did", "do", "does",
    "doing", "down", "during", "each", "few", "from", "further",
    "get", "got", "had", "has", "have", "having", "he", "her", "here",
    "hers", "herself", "him", "himself", "his", "how", "i", "its",
    "itself", "just", "me", "might", "more", "most", "must", "my",
    "myself", "nor", "now", "off", "once", "only", "other", "our",
    "ours", "ourselves", "out", "over", "own", "re", "same", "she",
    "should", "so", "some", "still", "than", "them", "themselves",
    "those", "through", "too", "under", "until", "up", "very", "we",
    "were", "what", "when", "where", "which", "while", "who", "whom",
    "why", "would", "you", "your", "yours", "yourself", "yourselves",
})


# ── Stage 1: CaseFolder ──────────────────────────────────────────────── #

class CaseFolder:
    """Lowercase all tokens."""

    def fold(self, tokens: list[str]) -> list[str]:
        """
        Args:
            tokens: List of raw token strings.
        Returns:
            List with every token lowercased.
        """
        return [t.lower() for t in tokens]


# ── Stage 2: PunctuationRemover ──────────────────────────────────────── #

class PunctuationRemover:
    """Strip non-alphanumeric characters from tokens, drop empty results."""

    def remove(self, tokens: list[str]) -> list[str]:
        """
        Args:
            tokens: List of casefolded tokens (may contain residual punctuation).
        Returns:
            List with punctuation stripped. Tokens that become empty are dropped.
        """
        result: list[str] = []
        for t in tokens:
            cleaned: str = re.sub(r"[^a-zA-Z0-9]", "", t)
            if cleaned:
                result.append(cleaned)
        return result


# ── Stage 3: StopWordFilter ──────────────────────────────────────────── #

class StopWordFilter:
    """Filter tokens against the stop word set."""

    def __init__(self) -> None:
        self._stop_words: frozenset[str] = STOP_WORDS

    def filter(self, tokens: list[str]) -> list[str]:
        """
        Args:
            tokens: List of cleaned, lowercased tokens.
        Returns:
            List with stop words removed.
        """
        return [t for t in tokens if t not in self._stop_words]


# ── Stage 4: Stemmer ─────────────────────────────────────────────────── #

class Stemmer:
    """
    Apply Porter stemmer. Must match C++ Preprocessor exactly.
    Uses NLTK's PorterStemmer implementation.
    """

    def __init__(self) -> None:
        self._stemmer = NLTKPorterStemmer()

    def stem(self, tokens: list[str]) -> list[str]:
        """
        Args:
            tokens: List of filtered tokens.
        Returns:
            List with each token replaced by its Porter stem.
        """
        return [self._stemmer.stem(t) for t in tokens]


# ── Normalizer (orchestrator) ─────────────────────────────────────────── #

class Normalizer:
    """
    Orchestrates the full normalization pipeline.

    Pipeline order: CaseFold → PunctuationRemove → StopWordFilter → Stem

    Owns all four sub-components. Instantiating Normalizer creates all of them.
    """

    def __init__(self) -> None:
        self._case_folder = CaseFolder()
        self._punctuation_remover = PunctuationRemover()
        self._stop_word_filter = StopWordFilter()
        self._stemmer = Stemmer()

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    def normalize(self, tokens: list[str]) -> list[str]:
        """
        Run the full normalization pipeline on a token list.

        Args:
            tokens: Raw token list from Tokenizer.
        Returns:
            Normalized token list ready for IndexBuilder.
            May be shorter than input (stop words removed, empty tokens dropped).
        """
        tokens = self._case_folder.fold(tokens)
        tokens = self._punctuation_remover.remove(tokens)
        tokens = self._stop_word_filter.filter(tokens)
        tokens = self._stemmer.stem(tokens)
        return tokens
