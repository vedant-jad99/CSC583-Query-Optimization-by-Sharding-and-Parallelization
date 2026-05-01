/****************************************************************
 *
 * @file boolean_engine.cpp
 * @description Phase 1 Boolean query engine implementation.
 *
 * @author Vedant Jadhav (vedantjadhav@arizona.edu)
 * @date April 3, 2026
 *
 ***************************************************************/

#include <iostream>
#include "boolean_engine.hpp"

int BooleanEngine::init(const std::string &bin_path) {
    int ret = decompressor.load(bin_path);
    if (-1 == ret) {
        std::cerr << "Error: Decompressor failed to load: " << bin_path << "\n";
        return -1;
    }

    ret = queryRunner.initIRSystem(
        decompressor.getIndex(),
        decompressor.getDocIDs()
    );

    if (-1 == ret) {
        std::cerr << "Error: QueryRunner failed to initialize IR system.\n";
        return -1;
    }

    return 0;
}

const std::vector<uint32_t> &BooleanEngine::query(const std::string &raw_query) {
    std::vector<std::string> normalized = preprocessor.process(raw_query);
    return queryRunner.runQuery(normalized);
}

/* Called by MasterEngine workers — normalized terms already computed once
 * by MasterEngine::preprocessor before fan-out. Zero extra preprocessing. */
const std::vector<uint32_t> &BooleanEngine::queryNormalized(
    const std::vector<std::string> &normalized_terms) {
    return queryRunner.runQuery(normalized_terms);
}
