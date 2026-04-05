/****************************************************************
 *
 * @file decompressor.cpp
 * @description VByte decoder and Decompressor implementation
 * @author Vedant Jadhav (vedantjadhav@arizona.edu)
 * @date April 3, 2026
 *
 ***************************************************************/

#include <stdexcept>
#include <iostream>

#include "decompressor.hpp"

/*==============================================================
 * VBDecoder
 *==============================================================*/

VBDecoder::VBDecoder(std::unordered_map<std::string,
                     std::pair<uint32_t, std::vector<uint8_t>>> compressed) : compressed_index(std::move(compressed)) {}

void VBDecoder::decode() {
    for (const auto &entry : compressed_index) {
        const std::string &term	= entry.first;
        const uint32_t docIDCount = entry.second.first;
        const std::vector<uint8_t> &bytes = entry.second.second;

        std::vector<uint32_t> posting_list;
        posting_list.reserve(docIDCount);

        uint32_t value   = 0;
        uint32_t shift   = 0;
        uint32_t prev_id = 0;

        for (const uint8_t byte : bytes) {
            value |= (static_cast<uint32_t>(byte & 0x7Fu)) << shift;
            shift += 7;

            if (byte & 0x80u) {
                const uint32_t abs_id = prev_id + value;
                posting_list.push_back(abs_id);
                universal_docids.insert(abs_id);
                prev_id = abs_id;
                value   = 0;
                shift   = 0;
            }
        }

        if (posting_list.size() != docIDCount) {
            std::cerr << "Warning: decoded doc ID count mismatch for term: "
                      << term << "\n";
        }

        decoded_index[term] = std::move(posting_list);
    }
}

std::unordered_map<std::string, std::vector<uint32_t>> VBDecoder::getIndex() {
    if (index_moved) {
        throw std::runtime_error("Error: Decoded index already moved.\n");
    }
    index_moved = true;
    return std::move(decoded_index);
}

std::set<uint32_t> VBDecoder::getDocIDs() {
    if (docids_moved) {
        throw std::runtime_error("Error: Universal doc ID set already moved.\n");
    }
    docids_moved = true;
    return std::move(universal_docids);
}


/*==============================================================
 * Decompressor
 *==============================================================*/

int Decompressor::load(const std::string &path) {
    bin_reader = std::make_unique<BinReader>(path);

    int ret = bin_reader->parse();
    if (-1 == ret) {
        std::cerr << "Error: BinReader failed to parse: " << path << "\n";
        bin_reader.reset();
        return -1;
    }

    VBDecoder vbd(bin_reader->getCompressedIndex());
    bin_reader.reset();

    vbd.decode();
    decoded_index = vbd.getIndex();
    universal_docids = vbd.getDocIDs();

    return 0;
}

std::unordered_map<std::string, std::vector<uint32_t>> Decompressor::getIndex() {
    if (index_moved) {
        throw std::runtime_error("Error: Decoded index already moved.\n");
    }
    index_moved = true;
    return std::move(decoded_index);
}

std::set<uint32_t> Decompressor::getDocIDs() {
    if (docids_moved) {
        throw std::runtime_error("Error: Universal doc ID set already moved.\n");
    }
    docids_moved = true;
    return std::move(universal_docids);
}
