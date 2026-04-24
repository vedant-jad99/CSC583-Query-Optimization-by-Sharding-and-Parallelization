/****************************************************************
 *
 * @file boolean_engine.hpp
 * @description Top-level Boolean query engine
 * @author Vedant Jadhav (vedantjadhav@arizona.edu)
 * @date April 3, 2026
 *
 ***************************************************************/

#ifndef BOOLEAN_ENGINE_HPP
#define BOOLEAN_ENGINE_HPP

#include <string>
#include <vector>
#include <cstdint>

#include "preprocessor.hpp"
#include "decompressor.hpp"
#include "ir_system.hpp"

class BooleanEngine {
    Preprocessor preprocessor;

    Decompressor decompressor;

    QueryRunner  queryRunner;

public:
    BooleanEngine() = default;

    int init(const std::string &bin_path);

    const std::vector<uint32_t> &query(const std::string &raw_query);
};

#endif /* BOOLEAN_ENGINE_HPP */
