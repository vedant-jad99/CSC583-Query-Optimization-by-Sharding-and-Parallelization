/****************************************************************
 *
 * @file test_preprocessor.cpp
 * @description Unit tests for Preprocessor::process().
 *              One test per pipeline stage so failures can be
 *              pinpointed exactly.
 *
 *  Stages tested (in pipeline order):
 *    1. Tokenizer      — [a-zA-Z0-9]+ extraction
 *    2. CaseFold       — everything lowercased
 *    3. PunctRemover   — non-alphanumeric stripped / empty dropped
 *    4. StopWordFilter — stop words removed
 *    5. Stemmer        — Porter stems match NLTK output
 *    6. Operators      — \and / \or / \not pass-through (and AND/OR/NOT)
 *    7. Full pipeline  — end-to-end combinations
 *
 * @author Vedant Jadhav (vedantjadhav@arizona.edu)
 * @date April 2026
 *
 ***************************************************************/

#include <iostream>
#include <string>
#include <vector>

#include "preprocessor.hpp"
#include "test_header.hpp"

/* ── helpers ──────────────────────────────────────────────────────────────── */

static void print_result(const std::string &name, bool passed) {
    std::cout << (passed ? "  PASS" : "  FAIL") << "  " << name << "\n";
}

/* Returns 1 and prints PASS, or returns 0 and prints FAIL + got/expected. */
static int check(const std::string &name,
                 const std::vector<std::string> &got,
                 const std::vector<std::string> &expected)
{
    test_counter++;
    if (got == expected) {
        print_result(name, true);
        return 1;
    }

    print_result(name, false);
    std::cout << "    expected: [";
    for (size_t i = 0; i < expected.size(); i++) {
        std::cout << "\"" << expected[i] << "\"";
        if (i + 1 < expected.size()) std::cout << ", ";
    }
    std::cout << "]\n    got:      [";
    for (size_t i = 0; i < got.size(); i++) {
        std::cout << "\"" << got[i] << "\"";
        if (i + 1 < got.size()) std::cout << ", ";
    }
    std::cout << "]\n";
    return 0;
}

/* ── Stage 1: Tokenizer ───────────────────────────────────────────────────── */
/* Verifies [a-zA-Z0-9]+ extraction — punctuation and spaces are delimiters. */

static int test_tokenizer_basic() {
    Preprocessor p;
    /* "hello world" — two plain tokens, stop words filtered but these are not */
    /* Use terms not in the stop-word list and short enough to survive stemming */
    auto got = p.process("sky lake");
    std::vector<std::string> expected = {"sky", "lake"};
    return check("tokenizer: plain alphanumeric tokens", got, expected);
}

static int test_tokenizer_splits_on_punctuation() {
    Preprocessor p;
    /* "sky.lake" should be treated as two tokens: sky and lake */
    auto got = p.process("sky.lake");
    std::vector<std::string> expected = {"sky", "lake"};
    return check("tokenizer: dot is a delimiter", got, expected);
}

static int test_tokenizer_splits_hyphen() {
    Preprocessor p;
    /* "sky-lake" — hyphen is not alphanumeric, splits into two tokens */
    auto got = p.process("sky-lake");
    std::vector<std::string> expected = {"sky", "lake"};
    return check("tokenizer: hyphen is a delimiter", got, expected);
}

static int test_tokenizer_numbers_kept() {
    Preprocessor p;
    /* Digits are alphanumeric and must be kept */
    auto got = p.process("mp3");
    std::vector<std::string> expected = {"mp3"};
    return check("tokenizer: digits kept in token", got, expected);
}

/* ── Stage 2: CaseFold ────────────────────────────────────────────────────── */

static int test_casefold_uppercase() {
    Preprocessor p;
    auto got = p.process("SKY");
    std::vector<std::string> expected = {"sky"};
    return check("casefold: uppercase → lowercase", got, expected);
}

static int test_casefold_mixed() {
    Preprocessor p;
    auto got = p.process("SkyLake");
    /* splits into one alphanumeric run "SkyLake" → lowercased → "skylake" */
    std::vector<std::string> expected = {"skylak"};  /* stem of "skylake" */
    return check("casefold: mixed case lowercased before stem", got, expected);
}

/* ── Stage 3: PunctuationRemover ─────────────────────────────────────────── */
/* After the tokenizer, tokens are already alphanumeric.                      */
/* These tests confirm punctuation embedded in a chunk does not leak through. */

static int test_punct_embedded_apostrophe() {
    Preprocessor p;
    /* "sky's" — apostrophe splits into "sky" and "s"; "s" is a stop-word-free
     * single char that survives (length 1 words are returned unchanged by
     * Porter, and "s" is not a stop word) */
    auto got = p.process("sky's");
    /* "sky" → not stop word → stem "sky"; "s" → not stop word → stem "s" */
    std::vector<std::string> expected = {"sky", "s"};
    return check("punct: apostrophe splits token", got, expected);
}

static int test_punct_leading_trailing() {
    Preprocessor p;
    /* "...sky..." — dots stripped, leaves "sky" */
    auto got = p.process("...sky...");
    std::vector<std::string> expected = {"sky"};
    return check("punct: leading/trailing dots stripped", got, expected);
}

/* ── Stage 4: StopWordFilter ──────────────────────────────────────────────── */

static int test_stopword_removed() {
    Preprocessor p;
    /* "the" is a stop word and must vanish */
    auto got = p.process("the");
    return check("stopword: 'the' removed", got, {});
}

static int test_stopword_multiple() {
    Preprocessor p;
    /* All stop words — result should be empty */
    auto got = p.process("a an the is was");
    return check("stopword: all stop words → empty result", got, {});
}

static int test_stopword_mixed_with_terms() {
    Preprocessor p;
    /* Stop words surrounding real terms */
    auto got = p.process("the sky is blue");
    /* "the" → stop; "sky" → "sky"; "is" → stop; "blue" → "blue" */
    std::vector<std::string> expected = {"sky", "blue"};
    return check("stopword: stop words removed, terms kept", got, expected);
}

/* ── Stage 5: Porter Stemmer ──────────────────────────────────────────────── */
/* Expected values verified against NLTK PorterStemmer().stem(word).          */

static int test_stem_plural_s() {
    Preprocessor p;
    auto got = p.process("cats");
    return check("stem: cats → cat", got, {"cat"});
}

static int test_stem_sses() {
    Preprocessor p;
    auto got = p.process("caresses");
    return check("stem: caresses → caress", got, {"caress"});
}

static int test_stem_ies() {
    Preprocessor p;
    auto got = p.process("ponies");
    return check("stem: ponies → poni", got, {"poni"});
}

static int test_stem_ed() {
    Preprocessor p;
    auto got = p.process("troubled");
    return check("stem: troubled → troubl", got, {"troubl"});
}

static int test_stem_ing() {
    Preprocessor p;
    auto got = p.process("running");
    return check("stem: running → run", got, {"run"});
}

static int test_stem_ing_double_cons() {
    Preprocessor p;
    /* "stemming" → double 'm' after stripping "ing" → single 'm' */
    auto got = p.process("stemming");
    return check("stem: stemming → stem", got, {"stem"});
}

static int test_stem_y_to_i() {
    Preprocessor p;
    /* step1c: y → i when stem contains a vowel */
    auto got = p.process("happiness");
    return check("stem: happiness → happi", got, {"happi"});
}

static int test_stem_ational() {
    Preprocessor p;
    /* step2: ational → ate */
    auto got = p.process("relational");
    return check("stem: relational → relat", got, {"relat"});
}

static int test_stem_ize() {
    Preprocessor p;
    auto got = p.process("digitize");
    return check("stem: digitize → digit", got, {"digit"});
}

static int test_stem_step5a_remove_e() {
    Preprocessor p;
    /* "relate": step5a removes trailing 'e' (m=2 for "relat") */
    auto got = p.process("relate");
    return check("stem: relate → relat (step5a)", got, {"relat"});
}

static int test_stem_step5a_keep_e() {
    Preprocessor p;
    /* "rate": step5a keeps 'e' (m=1, *o pattern for "rat") */
    auto got = p.process("rate");
    return check("stem: rate → rate (step5a keeps e)", got, {"rate"});
}

static int test_stem_short_word_unchanged() {
    Preprocessor p;
    /* Words of length <= 2 are returned unchanged by Porter */
    auto got = p.process("sky");   /* 3 chars — survives, no stem rule fires */
    return check("stem: short word unchanged", got, {"sky"});
}

/* ── Stage 6: Operators ───────────────────────────────────────────────────── */

static int test_operator_backslash_and() {
    Preprocessor p;
    auto got = p.process("sky \\and lake");
    std::vector<std::string> expected = {"sky", "\\and", "lake"};
    return check("operator: \\and passed through", got, expected);
}

static int test_operator_uppercase_AND() {
    Preprocessor p;
    auto got = p.process("sky AND lake");
    std::vector<std::string> expected = {"sky", "\\and", "lake"};
    return check("operator: AND → \\and", got, expected);
}

static int test_operator_backslash_or() {
    Preprocessor p;
    auto got = p.process("sky \\or lake");
    std::vector<std::string> expected = {"sky", "\\or", "lake"};
    return check("operator: \\or passed through", got, expected);
}

static int test_operator_uppercase_OR() {
    Preprocessor p;
    auto got = p.process("sky OR lake");
    std::vector<std::string> expected = {"sky", "\\or", "lake"};
    return check("operator: OR → \\or", got, expected);
}

static int test_operator_backslash_not() {
    Preprocessor p;
    auto got = p.process("sky \\not");
    std::vector<std::string> expected = {"sky", "\\not"};
    return check("operator: \\not passed through", got, expected);
}

static int test_operator_uppercase_NOT() {
    Preprocessor p;
    auto got = p.process("sky NOT lake");
    std::vector<std::string> expected = {"sky", "\\not", "lake"};
    return check("operator: NOT → \\not", got, expected);
}

static int test_operator_lowercase_and() {
    Preprocessor p;
    /* Lowercase "and" treated as operator (not stop-word-filtered) */
    auto got = p.process("sky and lake");
    std::vector<std::string> expected = {"sky", "\\and", "lake"};
    return check("operator: lowercase 'and' → \\and", got, expected);
}

/* ── Stage 7: Full pipeline ───────────────────────────────────────────────── */

static int test_pipeline_empty_input() {
    Preprocessor p;
    auto got = p.process("");
    return check("pipeline: empty string → empty result", got, {});
}

static int test_pipeline_whitespace_only() {
    Preprocessor p;
    auto got = p.process("   \t  ");
    return check("pipeline: whitespace only → empty result", got, {});
}

static int test_pipeline_stopwords_only() {
    Preprocessor p;
    auto got = p.process("the is a to");
    return check("pipeline: all stop words → empty result", got, {});
}

static int test_pipeline_boolean_query() {
    Preprocessor p;
    /* Typical RPN Boolean query */
    auto got = p.process("running dogs \\and");
    std::vector<std::string> expected = {"run", "dog", "\\and"};
    return check("pipeline: running dogs \\and → [run, dog, \\and]", got, expected);
}

static int test_pipeline_query_with_stopwords() {
    Preprocessor p;
    auto got = p.process("the running dogs \\and cats");
    std::vector<std::string> expected = {"run", "dog", "\\and", "cat"};
    return check("pipeline: stop words stripped in full query", got, expected);
}

static int test_pipeline_mixed_case_operators() {
    Preprocessor p;
    auto got = p.process("Running AND Cats");
    std::vector<std::string> expected = {"run", "\\and", "cat"};
    return check("pipeline: mixed case with AND operator", got, expected);
}

static int test_pipeline_punct_in_query() {
    Preprocessor p;
    /* Punctuation inside a query term splits it */
    auto got = p.process("sky.lake AND mountain");
    std::vector<std::string> expected = {"sky", "lake", "\\and", "mountain"};
    return check("pipeline: punct splits term in query", got, expected);
}

/* ── Suite entry point ────────────────────────────────────────────────────── */

int test_preprocessor() {
    int passed = 0;
    std::cout << "\n── Preprocessor tests ─────────────────────────────────────\n";

    std::cout << "\n  [Stage 1] Tokenizer\n";
    passed += test_tokenizer_basic();
    passed += test_tokenizer_splits_on_punctuation();
    passed += test_tokenizer_splits_hyphen();
    passed += test_tokenizer_numbers_kept();

    std::cout << "\n  [Stage 2] CaseFold\n";
    passed += test_casefold_uppercase();
    passed += test_casefold_mixed();

    std::cout << "\n  [Stage 3] PunctuationRemover\n";
    passed += test_punct_embedded_apostrophe();
    passed += test_punct_leading_trailing();

    std::cout << "\n  [Stage 4] StopWordFilter\n";
    passed += test_stopword_removed();
    passed += test_stopword_multiple();
    passed += test_stopword_mixed_with_terms();

    std::cout << "\n  [Stage 5] Porter Stemmer\n";
    passed += test_stem_plural_s();
    passed += test_stem_sses();
    passed += test_stem_ies();
    passed += test_stem_ed();
    passed += test_stem_ing();
    passed += test_stem_ing_double_cons();
    passed += test_stem_y_to_i();
    passed += test_stem_ational();
    passed += test_stem_ize();
    passed += test_stem_step5a_remove_e();
    passed += test_stem_step5a_keep_e();
    passed += test_stem_short_word_unchanged();

    std::cout << "\n  [Stage 6] Operators\n";
    passed += test_operator_backslash_and();
    passed += test_operator_uppercase_AND();
    passed += test_operator_backslash_or();
    passed += test_operator_uppercase_OR();
    passed += test_operator_backslash_not();
    passed += test_operator_uppercase_NOT();
    passed += test_operator_lowercase_and();

    std::cout << "\n  [Stage 7] Full pipeline\n";
    passed += test_pipeline_empty_input();
    passed += test_pipeline_whitespace_only();
    passed += test_pipeline_stopwords_only();
    passed += test_pipeline_boolean_query();
    passed += test_pipeline_query_with_stopwords();
    passed += test_pipeline_mixed_case_operators();
    passed += test_pipeline_punct_in_query();

    std::cout << "\n";
    return passed;
}
