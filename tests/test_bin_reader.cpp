#include <iostream>
#include <string>
#include <vector>
#include <cstdint>
#include <utility>
#include <unordered_map>

#include "binreader.hpp"
#include "test_header.hpp"

static const std::vector<std::string> test_files = {
	"./tests/test-bins/bin1.bin",
//	"./test-bins/bin2.bin",
//	"./test-bins/bin3.bin",
//	"./test-bins/file.bin",
//	"./test-bins/test.bin",
};

static const std::vector<size_t> test_files_sizes = {
	26,
};

static const std::vector<std::unordered_map<std::string, std::pair<uint32_t, std::vector<uint8_t>>>> maps {
	{{"JKLMN", {3, {0x81, 0x82, 0x83}}}},
};

static int test_bin_reader_construct(std::string filepath) {
	BinReader reader(filepath);
	const std::string bin_path = reader.getPath();
	return (int)(filepath == bin_path);
}

static int test_bin_reader_parse(std::string filepath, int index) {
	BinReader reader(filepath);
	int ret = reader.parse();
	if (ret != -1) {
		return (int)(reader.getSize() == test_files_sizes[index]);
	}
	return 0;
}

static int test_bin_reader_parse_getCompressedIndex_fail(std::string filepath, int index) {
	BinReader reader(filepath);
	int ret = reader.parse();

	if (ret != -1) {
		if (reader.getSize() != test_files_sizes[index]) {
			return 0;
		}
		const auto compressed_index = reader.getCompressedIndex();
		try {
			const auto retry_index = reader.getCompressedIndex();
			return 0;
		} catch (const std::runtime_error &e) {
			std::cerr << "Test: BinReader: Exception expected : " << e.what() << "\n";
		}
	}

	return 1;
}

static int test_bin_reader_parse_correct(std::string filepath, int index) {
	BinReader reader(filepath);
	int ret = reader.parse();
	if (ret != -1) {
		if (reader.getSize() == test_files_sizes[index]) {
			const auto compressed_index = reader.getCompressedIndex();
			for (auto const &m : maps) {
				for (auto const &it : m) {
					if (compressed_index.find(it.first) != compressed_index.end()) {
						const auto&ele = compressed_index.at(it.first);
						if (ele.first != it.second.first) {
							return 0;
						}
						for (size_t i = 0; i < it.second.second.size(); i++) {
							if (it.second.second[i] != ele.second[i]) {
								return 0;
							}
						}
					} else {
						return 0;
					}
				}
			}
		} else {
			return 0;
		}
	}

	return 1;
}

int test_bin_reader() {
	int counter = 0;
	bool retval = 0;
	for (std::string const &file : test_files) {
		counter += test_bin_reader_construct(file);
	}
	retval = ((size_t)counter == test_files.size());
	if (!retval) {
		// TODO: Add test failure message.
		return 0;
	}

	counter = 0; int index = 0;
	for (std::string const &file : test_files) {
		counter += test_bin_reader_parse(file, index++);
	}
	retval = (counter == index);
	if (!retval) {
		// TODO: Add test failure message.
		return 0;
	}

	counter = 0; index = 0;
	for (std::string const &file : test_files) {
		counter += test_bin_reader_parse_getCompressedIndex_fail(file, index++);
	}
	retval = (counter == index);
	if (!retval) {
		// TODO: Add test failure message.
		return 0;
	}

	counter = 0; index = 0;
	for (std::string const &file : test_files) {
		counter += test_bin_reader_parse_correct(file, index++);
	}
	retval = (counter == index);
	if (!retval) {
		// TODO: Add test failure message.
		return 0;
	}

	test_counter++;
	return (int)retval;
}
