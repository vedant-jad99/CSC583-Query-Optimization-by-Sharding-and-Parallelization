/****************************************************************
 *
 * @file decompressor.hpp
 * @description Header for the main Decompressor to reconstruct
 * the inverted index
 * @author Vedant Jadhav (vedantjadhav@arizona.edu)
 * @date April 3, 2026
 *
 ***************************************************************/

#ifndef DECOMPRESSOR_HPP
#define DECOMPRESSOR_HPP

#include <set>
#include <string>
#include <vector>
#include <memory>
#include <cstdint>
#include <utility>
#include <unordered_map>

#include "binreader.hpp"

class VBDecoder {
    bool index_moved  = false;

    bool docids_moved = false;

    std::unordered_map<std::string, std::pair<uint32_t, std::vector<uint8_t>>> compressed_index;

    std::unordered_map<std::string, std::vector<uint32_t>> decoded_index;

    std::set<uint32_t> universal_docids;

public:
    explicit VBDecoder(std::unordered_map<std::string, std::pair<uint32_t, std::vector<uint8_t>>> compressed);

    void decode();

    std::unordered_map<std::string, std::vector<uint32_t>> getIndex();

    std::set<uint32_t> getDocIDs();
};


class Decompressor {
    bool index_moved  = false;

    bool docids_moved = false;

    std::unique_ptr<BinReader> bin_reader;

    std::unordered_map<std::string, std::vector<uint32_t>> decoded_index;

    std::set<uint32_t> universal_docids;

public:
    Decompressor() = default;

    int load(const std::string &path);

    std::unordered_map<std::string, std::vector<uint32_t>> getIndex();

    std::set<uint32_t> getDocIDs();
};

#endif /* DECOMPRESSOR_HPP */
