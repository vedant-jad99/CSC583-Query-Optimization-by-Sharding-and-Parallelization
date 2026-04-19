#include <string>
#include <vector>
#include <cstdint>
#include <utility>
#include <unordered_map>

#include "decompressor.hpp"
#include "test_header.hpp"

static const std::unordered_map<std::string, std::pair<uint32_t, std::vector<uint8_t>>> input {
	{"word1", {4, {0x81, 0x44, 0xb2, 0x1, 0x89, 0x85}}},
	{"word2", {2, {0x55, 0x22, 0xb3, 0x89}}}
};

static const std::unordered_map<std::string, std::pair<uint32_t, std::vector<uint8_t>>> input2 {
	{"word1", {4, {0x81, 0x44, 0xb2, 0x1, 0x89, 0x85}}},
	{"word2", {2, {0x55, 0x22, 0xb3, 0x89}}}
};

static const std::unordered_map<std::string, std::pair<uint32_t, std::vector<uint8_t>>> input3 {
    {"word1", {4, {0x81, 0x44, 0xb2, 0x1, 0x89, 0x85}}},
    {"word2", {2, {0x55, 0x22, 0xb3, 0x89}}}
};

static const std::unordered_map<std::string, std::vector<uint32_t>> expected_index {
    {"word1", {1, 6469, 7622, 7627}},
    {"word2", {840021, 840030}},
};

static const std::vector<std::string> wordList = {
	"word1",
	"word2",
};

static const std::vector<uint32_t> ids = {
	1, 6469, 7622, 7627, 840021, 840030,
};

static int test_vb_decoder_getIndex() {
	VBDecoder vbd(input);
	vbd.decode();

	auto index = vbd.getIndex();
	for (const auto &word : wordList) {
		if (index.find(word) == index.end()) {
			return 0;
		}
	}

	try {
		auto index2 = vbd.getIndex();
		return 0;
	} catch (const std::runtime_error &e) {
		std::cerr << "Test: VBDecoder: Exception expected : " << e.what() << "\n";
	}

	return 1;
}

static int test_vb_decoder_getDocIDs() {
	VBDecoder vbd(input2);
	vbd.decode();

	auto docIds = vbd.getDocIDs();
	int i = 0;
	for (const auto &id : docIds) {
		if (id != ids[i++]) { return 0; }
	}

	try {
		auto docIds2 = vbd.getDocIDs();
		return 0;
	} catch (const std::runtime_error &e) {
		std::cerr << "Test: VBDecoder: Exception expected : " << e.what() << "\n";
	}

	return 1;
}

static int test_vb_decoder_decode() {
	VBDecoder vbd(input3);
    vbd.decode();

    auto index = vbd.getIndex();

    for (const auto &word : wordList) {
        auto it = index.find(word);
        if (it == index.end()) { return 0; }

        const auto &expected = expected_index.at(word);
        const auto &actual   = it->second;

        if (actual.size() != expected.size()) { return 0; }

        for (size_t i = 0; i < expected.size(); i++) {
            if (actual[i] != expected[i]) { return 0; }
        }
    }

    return 1;
}

int test_vb_decoder() {
	int retval = 0;
	retval = test_vb_decoder_getIndex();
	if (retval == 0) {
		// TODO: Add test failure message.
		return 0;
	}

	retval = test_vb_decoder_getDocIDs();
	if (retval == 0) {
		// TODO: Add test failure message.
		return 0;
	}

	retval = test_vb_decoder_decode();
    if (retval == 0) {
		// TODO: Add test failure message.
		return 0;
	}

	test_counter++;
	return retval;
}
