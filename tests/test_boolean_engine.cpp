/****************************************************************
 *
 * @file test_boolean_engine.cpp
 * @description Tests for BooleanEngine end-to-end
 * @author Vedant Jadhav (vedantjadhav@arizona.edu)
 * @date April 3, 2026
 *
 ***************************************************************/

#include <set>
#include <string>
#include <vector>
#include <cstdint>
#include <algorithm>

#include "boolean_engine.hpp"
#include "test_header.hpp"

static const std::string valid_bin   = "./tests/test-bins/bin1.bin";
static const std::string invalid_bin = "./tests/test-bins/nonexistent.bin";

/*--------------------------------------------------------------
 * Test: init() succeeds on valid bin file
 *------------------------------------------------------------*/
static int test_engine_init_valid() {
    BooleanEngine engine;
    return (engine.init(valid_bin) == 0) ? 1 : 0;
}

/*--------------------------------------------------------------
 * Test: init() fails on invalid bin file
 *------------------------------------------------------------*/
static int test_engine_init_invalid() {
    BooleanEngine engine;
    return (engine.init(invalid_bin) == -1) ? 1 : 0;
}

/*--------------------------------------------------------------
 * Test: single term query — term exists
 * bin1.bin: JKLMN → [1, 3, 6]
 * query: "JKLMN"
 * expected: [1, 3, 6]
 *------------------------------------------------------------*/
static int test_engine_query_single_term() {
    BooleanEngine engine;
    if (engine.init(valid_bin) == -1) { return 0; }

    auto results = engine.query("JKLMN");

    std::vector<uint32_t> expected = {1, 3, 6};
    return (results == expected) ? 1 : 0;
}

/*--------------------------------------------------------------
 * Test: single term query — term does not exist
 * expected: []
 *------------------------------------------------------------*/
static int test_engine_query_missing_term() {
    BooleanEngine engine;
    if (engine.init(valid_bin) == -1) { return 0; }

    auto results = engine.query("nonexistent");
    return results.empty() ? 1 : 0;
}

/*--------------------------------------------------------------
 * Test: NOT query — NOT on existing term
 * bin1.bin: JKLMN → [1, 3, 6], universal = {1, 3, 6}
 * query: "JKLMN \\not"
 * expected: [] (all docs are in JKLMN)
 *------------------------------------------------------------*/
static int test_engine_query_not() {
    BooleanEngine engine;
    if (engine.init(valid_bin) == -1) { return 0; }

    auto results = engine.query("JKLMN \\not");
    return results.empty() ? 1 : 0;
}

/*--------------------------------------------------------------
 * Test: NOT on missing term
 * query: "nonexistent \\not"
 * expected: full universal set [1, 3, 6]
 *------------------------------------------------------------*/
static int test_engine_query_not_missing() {
    BooleanEngine engine;
    if (engine.init(valid_bin) == -1) { return 0; }

    auto results = engine.query("nonexistent \\not");
    std::vector<uint32_t> expected = {1, 3, 6};
    return (results == expected) ? 1 : 0;
}

/*--------------------------------------------------------------
 * Test: malformed query — operator with no operands
 * expected: throws runtime_error
 *------------------------------------------------------------*/
static int test_engine_query_malformed() {
    BooleanEngine engine;
    if (engine.init(valid_bin) == -1) { return 0; }

    try {
        auto results = engine.query("\\not");
        return 0;  /* Should not reach here */
    } catch (const std::runtime_error &e) {
        std::cerr << "Test: BooleanEngine: Exception expected: " << e.what();
    }

    return 1;
}

/*--------------------------------------------------------------
 * Test: empty query string
 * expected: throws or returns empty — either is acceptable
 *------------------------------------------------------------*/
static int test_engine_query_empty() {
    BooleanEngine engine;
    if (engine.init(valid_bin) == -1) { return 0; }

    try {
        auto results = engine.query("");
        /* Empty input → empty token list → stack has 0 elements → throws */
        return 0;
    } catch (const std::runtime_error &e) {
        std::cerr << "Test: BooleanEngine: Exception expected: " << e.what();
    }

    return 1;
}

/*--------------------------------------------------------------
 * Suite entry point
 *------------------------------------------------------------*/
int test_boolean_engine() {
    int retval = 0;

    retval = test_engine_init_valid();
    if (!retval) { return 0; }

    retval = test_engine_init_invalid();
    if (!retval) { return 0; }

    retval = test_engine_query_single_term();
    if (!retval) { return 0; }

    retval = test_engine_query_missing_term();
    if (!retval) { return 0; }

    retval = test_engine_query_not();
    if (!retval) { return 0; }

    retval = test_engine_query_not_missing();
    if (!retval) { return 0; }

    retval = test_engine_query_malformed();
    if (!retval) { return 0; }

    retval = test_engine_query_empty();
    if (!retval) { return 0; }

    test_counter++;
    return retval;
}
