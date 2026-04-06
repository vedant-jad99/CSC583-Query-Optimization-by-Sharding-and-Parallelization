import pytest
from tokenizer import Tokenizer


@pytest.fixture
def tok():
    return Tokenizer()


class TestTokenizerBasic:
    def test_simple_sentence(self, tok):
        assert tok.tokenize("hello world") == ["hello", "world"]

    def test_mixed_case(self, tok):
        assert tok.tokenize("Hello World") == ["Hello", "World"]

    def test_numbers(self, tok):
        assert tok.tokenize("doc 42 has 7 terms") == ["doc", "42", "has", "7", "terms"]

    def test_alphanumeric_tokens(self, tok):
        assert tok.tokenize("http2 mp3 h264") == ["http2", "mp3", "h264"]


class TestTokenizerPunctuation:
    def test_commas_periods(self, tok):
        assert tok.tokenize("hello, world. goodbye!") == ["hello", "world", "goodbye"]

    def test_hyphens_split(self, tok):
        assert tok.tokenize("well-known state-of-the-art") == [
            "well", "known", "state", "of", "the", "art"
        ]

    def test_apostrophes_split(self, tok):
        result = tok.tokenize("don't can't won't")
        assert result == ["don", "t", "can", "t", "won", "t"]

    def test_parentheses_brackets(self, tok):
        assert tok.tokenize("(information) [retrieval] {system}") == [
            "information", "retrieval", "system"
        ]

    def test_quotes(self, tok):
        assert tok.tokenize('"hello" \'world\'') == ["hello", "world"]

    def test_slashes(self, tok):
        assert tok.tokenize("and/or input/output") == ["and", "or", "input", "output"]

    def test_colons_semicolons(self, tok):
        assert tok.tokenize("key: value; next: item") == ["key", "value", "next", "item"]

    def test_pure_punctuation_returns_empty(self, tok):
        assert tok.tokenize("!@#$%^&*()") == []

    def test_ellipsis(self, tok):
        assert tok.tokenize("wait... what?!") == ["wait", "what"]


class TestTokenizerWhitespace:
    def test_multiple_spaces(self, tok):
        assert tok.tokenize("hello   world") == ["hello", "world"]

    def test_tabs(self, tok):
        assert tok.tokenize("hello\tworld") == ["hello", "world"]

    def test_newlines(self, tok):
        assert tok.tokenize("hello\nworld\nfoo") == ["hello", "world", "foo"]

    def test_mixed_whitespace(self, tok):
        assert tok.tokenize("  hello \t world \n foo  ") == ["hello", "world", "foo"]

    def test_leading_trailing_whitespace(self, tok):
        assert tok.tokenize("   hello   ") == ["hello"]


class TestTokenizerEdge:
    def test_empty_string(self, tok):
        assert tok.tokenize("") == []

    def test_only_whitespace(self, tok):
        assert tok.tokenize("   \t\n  ") == []

    def test_single_character(self, tok):
        assert tok.tokenize("a") == ["a"]

    def test_single_number(self, tok):
        assert tok.tokenize("7") == ["7"]

    def test_very_long_token(self, tok):
        long = "a" * 10000
        assert tok.tokenize(long) == [long]

    def test_unicode_stripped(self, tok):
        """Non-ASCII characters are not in [a-zA-Z0-9], so they get stripped."""
        result = tok.tokenize("café résumé naïve")
        assert result == ["caf", "r", "sum", "na", "ve"]

    def test_email_like(self, tok):
        result = tok.tokenize("user@example.com")
        assert result == ["user", "example", "com"]

    def test_url_like(self, tok):
        result = tok.tokenize("https://example.com/path?q=1")
        assert result == ["https", "example", "com", "path", "q", "1"]

    def test_numeric_only_string(self, tok):
        assert tok.tokenize("12345 67890") == ["12345", "67890"]
