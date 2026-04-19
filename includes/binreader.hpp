/****************************************************************
 *
 * @file binreader.hpp
 * @description Header for reading and parsing the bin file
 * @author Vedant Jadhav (vedantjadhav@arizona.edu)
 * @date April 3, 2026
 *
 ***************************************************************/

#ifndef BINREADER_HPP
#define BINREADER_HPP

#include <string>
#include <vector>
#include <utility>
#include <cstdint>
#include <unordered_map>

#define MAGIC_STRING	"INVI_100" /* INVerted Index v1.0.0 */
#define MAGIC_STRING_SZ	8

#define VB_ENCODING_CONTROL_BITMASK	0x80U

class BinReader {
	bool index_moved = false;

	size_t bin_size = 0;

	const std::string bin_path;

	std::unordered_map<std::string, std::pair<uint32_t, std::vector<uint8_t>>> compressed_index;

	int parseHelper(const char * const, const size_t);

public:
	BinReader(std::string);

	int parse();

	std::unordered_map<std::string, std::pair<uint32_t, std::vector<uint8_t>>> getCompressedIndex();

	const std::string &getPath() const;

	inline size_t getSize() const { return bin_size; }
};

#endif /* BINREADER_HPP */
