/****************************************************************
 *
 * @file test_decompressor.cpp
 * @description Tests for Decompressor and VBDecoder integration
 * @author Vedant Jadhav (vedantjadhav@arizona.edu)
 * @date April 3, 2026
 *
 ***************************************************************/

#include <set>
#include <string>
#include <vector>
#include <cstdint>
#include <iostream>
#include <stdexcept>
#include <unordered_map>

#include "decompressor.hpp"
#include "test_header.hpp"

static const std::string valid_bin   = "./tests/test-bins/bin1.bin";
static const std::string invalid_bin = "./tests/test-bins/nonexistent.bin";

static const std::unordered_map<std::string, std::vector<uint32_t>> expected_index {
    {"JKLMN", {1, 3, 6}},
};

static const std::set<uint32_t> expected_docids {1, 3, 6};

/*--------------------------------------------------------------
 * Test: load() succeeds on valid bin file
 *------------------------------------------------------------*/
static int test_decompressor_load_valid() {
    Decompressor d;
    int ret = d.load(valid_bin);
    return (ret == 0) ? 1 : 0;
}

/*--------------------------------------------------------------
 * Test: load() fails on invalid/nonexistent bin file
 *------------------------------------------------------------*/
static int test_decompressor_load_invalid() {
    Decompressor d;
    int ret = d.load(invalid_bin);
    return (ret == -1) ? 1 : 0;
}

/*--------------------------------------------------------------
 * Test: getIndex() returns correct decoded index
 *       and throws on second call
 *------------------------------------------------------------*/
static int test_decompressor_getIndex() {
    Decompressor d;
    if (d.load(valid_bin) == -1) { return 0; }

    auto index = d.getIndex();

    for (const auto &entry : expected_index) {
        auto it = index.find(entry.first);
        if (it == index.end()) { return 0; }

        const auto &actual   = it->second;
        const auto &expected = entry.second;

        if (actual.size() != expected.size()) { return 0; }
        for (size_t i = 0; i < expected.size(); i++) {
            if (actual[i] != expected[i]) { return 0; }
        }
    }

    try {
        auto index2 = d.getIndex();
        return 0;
    } catch (const std::runtime_error &e) {
        std::cerr << "Test: Decompressor: Exception expected: " << e.what() << "\n";
    }

    return 1;
}

/*--------------------------------------------------------------
 * Test: getDocIDs() returns correct universal set
 *       and throws on second call
 *------------------------------------------------------------*/
static int test_decompressor_getDocIDs() {
    Decompressor d;
    if (d.load(valid_bin) == -1) { return 0; }

    auto docids = d.getDocIDs();

    if (docids != expected_docids) { return 0; }

    try {
        auto docids2 = d.getDocIDs();
        return 0;
    } catch (const std::runtime_error &e) {
        std::cerr << "Test: Decompressor: Exception expected: " << e.what() << "\n";
    }

    return 1;
}

/*--------------------------------------------------------------
 * Test: getIndex() and getDocIDs() both fail after
 *       a failed load() — nothing should be returned
 *------------------------------------------------------------*/
static int test_decompressor_no_data_after_failed_load() {
    Decompressor d;
    d.load(invalid_bin);

    auto index  = d.getIndex();
    auto docids = d.getDocIDs();

    return (index.empty() && docids.empty()) ? 1 : 0;
}

/*--------------------------------------------------------------
 * Suite entry point
 *------------------------------------------------------------*/
int test_decompressor() {
    int retval = 0;

    retval = test_decompressor_load_valid();
    if (!retval) { return 0; }

    retval = test_decompressor_load_invalid();
    if (!retval) { return 0; }

    retval = test_decompressor_getIndex();
    if (!retval) { return 0; }

    retval = test_decompressor_getDocIDs();
    if (!retval) { return 0; }

    retval = test_decompressor_no_data_after_failed_load();
    if (!retval) { return 0; }

    test_counter++;
    return retval;
}
