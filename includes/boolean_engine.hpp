/****************************************************************
 *
 * @file boolean_engine.hpp
 * @description Phase 1 Boolean query engine.
 *              Used standalone for Phase 1 and as a shard-level
 *              building block owned by MasterEngine for Phase 2/3.
 *
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

    /* Phase 1 entry point — preprocesses raw query internally.
     * Returns const ref into QueryRunner::q_result (member storage).
     * Valid until the next call to query() or queryNormalized(). */
    const std::vector<uint32_t> &query(const std::string &raw_query);

    /* Phase 2/3 entry point — accepts pre-normalized terms from MasterEngine.
     * MasterEngine preprocesses the raw query exactly once and passes the
     * same normalized terms to all N engines in parallel via this method.
     * Returns const ref into QueryRunner::q_result — zero copy.
     * Valid until the next call on this engine, which is guaranteed not to
     * happen until MasterEngine has completed the merge step. */
    const std::vector<uint32_t> &queryNormalized(
        const std::vector<std::string> &normalized_terms);
};

#endif /* BOOLEAN_ENGINE_HPP */
