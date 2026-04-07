import pytest
from normalizer import (
    CaseFolder, PunctuationRemover, StopWordFilter, Stemmer, Normalizer, STOP_WORDS
)


# ── CaseFolder ────────────────────────────────────────────────────────

class TestCaseFolder:
    def test_lowercase(self):
        assert CaseFolder().fold(["Hello", "WORLD"]) == ["hello", "world"]

    def test_already_lower(self):
        assert CaseFolder().fold(["hello"]) == ["hello"]

    def test_mixed(self):
        assert CaseFolder().fold(["HeLLo", "WoRlD"]) == ["hello", "world"]

    def test_numbers_unchanged(self):
        assert CaseFolder().fold(["abc123", "DEF456"]) == ["abc123", "def456"]

    def test_empty_list(self):
        assert CaseFolder().fold([]) == []

    def test_empty_string_token(self):
        assert CaseFolder().fold([""]) == [""]


# ── PunctuationRemover ────────────────────────────────────────────────

class TestPunctuationRemover:
    def test_no_punct(self):
        assert PunctuationRemover().remove(["hello", "world"]) == ["hello", "world"]

    def test_trailing_punct(self):
        assert PunctuationRemover().remove(["hello!", "world."]) == ["hello", "world"]

    def test_leading_punct(self):
        assert PunctuationRemover().remove(["(hello", "[world"]) == ["hello", "world"]

    def test_embedded_punct(self):
        assert PunctuationRemover().remove(["he-llo", "wo.rld"]) == ["hello", "world"]

    def test_all_punct_dropped(self):
        assert PunctuationRemover().remove(["!!!", "---", "..."]) == []

    def test_empty_list(self):
        assert PunctuationRemover().remove([]) == []

    def test_mixed(self):
        assert PunctuationRemover().remove(["hello!", "###", "world?"]) == ["hello", "world"]

    def test_numbers_preserved(self):
        assert PunctuationRemover().remove(["abc123", "45.6"]) == ["abc123", "456"]

    def test_underscore_removed(self):
        assert PunctuationRemover().remove(["hello_world"]) == ["helloworld"]


# ── StopWordFilter ────────────────────────────────────────────────────

class TestStopWordFilter:
    def test_removes_stop_words(self):
        tokens = ["the", "quick", "brown", "fox"]
        assert StopWordFilter().filter(tokens) == ["quick", "brown", "fox"]

    def test_all_stop_words(self):
        tokens = ["the", "a", "is", "and", "or"]
        assert StopWordFilter().filter(tokens) == []

    def test_no_stop_words(self):
        tokens = ["retrieval", "index", "query"]
        assert StopWordFilter().filter(tokens) == ["retrieval", "index", "query"]

    def test_empty_list(self):
        assert StopWordFilter().filter([]) == []

    def test_case_sensitive(self):
        """Stop words are lowercase; uppercase versions should NOT be filtered."""
        tokens = ["The", "AND", "OR"]
        result = StopWordFilter().filter(tokens)
        assert result == ["The", "AND", "OR"]

    def test_common_stop_words_present(self):
        common = ["a", "an", "the", "is", "are", "was", "were", "be",
                   "been", "being", "have", "has", "had", "do", "does",
                   "did", "will", "would", "should", "can", "could",
                   "in", "on", "at", "by", "for", "with", "about",
                   "to", "from", "of", "and", "or", "not", "but",
                   "if", "this", "that", "it", "he", "she", "they",
                   "we", "you", "i", "my", "your", "his", "her"]
        for w in common:
            assert w in STOP_WORDS, f"'{w}' should be a stop word"


# ── Stemmer ───────────────────────────────────────────────────────────

class TestStemmer:
    def test_basic_stemming(self):
        tokens = ["running", "runs", "runner"]
        result = Stemmer().stem(tokens)
        assert result == ["run", "run", "runner"]

    def test_retrieval_stem(self):
        assert Stemmer().stem(["retrieval"]) == ["retriev"]

    def test_information_stem(self):
        assert Stemmer().stem(["information"]) == ["inform"]

    def test_already_stemmed(self):
        assert Stemmer().stem(["run"]) == ["run"]

    def test_plurals(self):
        result = Stemmer().stem(["documents", "queries", "indexes"])
        assert result == ["document", "queri", "index"]

    def test_empty_list(self):
        assert Stemmer().stem([]) == []

    def test_past_tense(self):
        result = Stemmer().stem(["computed", "searched", "indexed"])
        assert result == ["comput", "search", "index"]

    def test_gerunds(self):
        result = Stemmer().stem(["computing", "searching", "indexing"])
        assert result == ["comput", "search", "index"]

    def test_comparative(self):
        result = Stemmer().stem(["faster", "larger", "smaller"])
        assert result == ["faster", "larger", "smaller"]


# ── Normalizer (full pipeline) ────────────────────────────────────────

class TestNormalizerPipeline:
    @pytest.fixture
    def norm(self):
        return Normalizer()

    def test_full_pipeline(self, norm):
        tokens = ["The", "Quick", "BROWN", "Fox"]
        result = norm.normalize(tokens)
        # casefold: the, quick, brown, fox
        # punct remove: the, quick, brown, fox (no change)
        # stop filter: quick, brown, fox ("the" removed)
        # stem: quick, brown, fox
        assert result == ["quick", "brown", "fox"]

    def test_pipeline_order_matters(self, norm):
        """CaseFold MUST happen before StopWordFilter (which checks lowercase)."""
        tokens = ["THE", "Information", "Retrieval"]
        result = norm.normalize(tokens)
        # casefold: the, information, retrieval
        # stop: information, retrieval (the removed)
        # stem: inform, retriev
        assert result == ["inform", "retriev"]

    def test_punct_then_stop(self, norm):
        tokens = ["...the", "information!", "(is)", "retrieval."]
        result = norm.normalize(tokens)
        # casefold: ...the, information!, (is), retrieval.
        # punct: the, information, is, retrieval
        # stop: information, retrieval
        # stem: inform, retriev
        assert result == ["inform", "retriev"]

    def test_all_stop_words(self, norm):
        tokens = ["The", "A", "Is", "And", "Or", "Not"]
        result = norm.normalize(tokens)
        assert result == []

    def test_empty_input(self, norm):
        assert norm.normalize([]) == []

    def test_all_punctuation_tokens(self, norm):
        tokens = ["!!!", "---", "..."]
        assert norm.normalize(tokens) == []

    def test_real_sentence(self, norm):
        tokens = ["Information", "retrieval", "is", "the", "activity",
                   "of", "obtaining", "information"]
        result = norm.normalize(tokens)
        assert "inform" in result
        assert "retriev" in result
        assert "activ" in result
        assert "obtain" in result
        assert "the" not in result
        assert "is" not in result
        assert "of" not in result

    def test_duplicate_terms_preserved(self, norm):
        """Normalizer doesn't deduplicate — that's IndexBuilder's job."""
        tokens = ["information", "information", "information"]
        result = norm.normalize(tokens)
        assert result == ["inform", "inform", "inform"]

    def test_numbers_pass_through(self, norm):
        tokens = ["section", "42", "page", "7"]
        result = norm.normalize(tokens)
        assert "42" in result
        assert "7" in result
