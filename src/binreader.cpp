/****************************************************************
 *
 * @file binreader.cpp
 * @description Implementation file for the bin file reader
 * @author Vedant Jadhav (vedantjadhav@arizona.edu)
 * @date April 3, 2026
 *
 ***************************************************************/

#include <cstring>
#include <iostream>
#include <fcntl.h>
#include <unistd.h>
#include <sys/mman.h>
#include <sys/stat.h>

#include "binreader.hpp"

BinReader::BinReader(std::string path) : bin_path(path) {}

const std::string &BinReader::getPath() const {
	return bin_path;
}

std::unordered_map<std::string, std::pair<uint32_t, std::vector<uint8_t>>> BinReader::getCompressedIndex() {
	if (index_moved) {
		throw std::runtime_error("Error: Compressed index already moved.\n");
	}
	index_moved = true;
	return std::move(compressed_index);
}

int BinReader::parseHelper(const char * const f_addr, const size_t size) {
	if (nullptr == f_addr || MAP_FAILED == f_addr) {
		return -1;
	}
	if (size == 0 || size <= MAGIC_STRING_SZ + 10) { // Size of uint32_t * 2 + size of uint16_t
		return 0;
	}

	int cmp = std::memcmp(f_addr, MAGIC_STRING, (size_t)MAGIC_STRING_SZ);
	if (cmp != 0) {
		std::cerr << "Parsing error: Magic string not equal\n";
		return -1;
	}
	uint32_t index_size = 0;
	std::memcpy(&index_size, f_addr + MAGIC_STRING_SZ, 4);
	int offset = MAGIC_STRING_SZ + 4; // Size of uint32_t

	for (uint32_t i = 0; i < index_size; i++) {
		uint16_t term_length = 0; uint32_t docIDCount = 0;
		std::memcpy(&term_length, f_addr + offset, 2);
		std::memcpy(&docIDCount, f_addr + offset + 2, 4);
		offset += 6; // Size of uint16_t + size of uint32_t

		if (term_length > size - offset) { return -1; }

		std::string term; std::vector<uint8_t> vec;
		term.assign(f_addr + offset, term_length);
		offset += term_length;

		uint32_t id = 0;
		while (id < docIDCount) {
			uint8_t *byte = (uint8_t *)(f_addr + offset);
			vec.push_back(*byte);
			offset += 1;
			if (*byte & VB_ENCODING_CONTROL_BITMASK) {
				id++;
			}
			if ((size_t)offset > size) { return -1; }
		}

		compressed_index[term] = std::make_pair(docIDCount, vec);
	}

	return 0;
}

int BinReader::parse() {
	const char *filepath = bin_path.c_str();
	int fd = open(filepath, O_RDONLY);
	if (-1 == fd) {
		std::cerr << "Error opening file: " << bin_path << "\n";
		return -1;
	}

	struct stat sb;
	if (-1 == fstat(fd, &sb)) {
		std::cerr << "Error fetching file information for: " << bin_path << "\n";
		close(fd);
		return -1;
	}

	bin_size = sb.st_size;
	char *addr = static_cast<char *>(mmap(NULL, bin_size, PROT_READ, MAP_PRIVATE, fd, 0));
	if (MAP_FAILED == addr) {
		std::cerr << "Error mapping file: " << bin_path << "\n";
		close(fd);
		return -1;
	}

	int retval = parseHelper(addr, bin_size);
	if (-1 == retval) {
		std::cerr << "Error: Parsing failed for bin file: " << bin_path << "\n";
	}

	if (-1 == munmap(addr, bin_size)) {
		std::cerr << "Error unmapping file: " << bin_path << "\n";
		retval = -1;
	}

	close(fd);
	return retval;
}
