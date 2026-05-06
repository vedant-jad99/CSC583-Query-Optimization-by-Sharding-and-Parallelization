/****************************************************************
 *
 * @file master_engine.hpp
 * @description Phase 2/3 sharded query engine.
 *
 *              Owns N BooleanEngine instances, one per shard.
 *              Phase 2: sequential init, sequential query fan-out.
 *              Phase 3: parallel init via std::async, parallel
 *                       query fan-out via persistent thread pool.
 *
 *              Merge strategy: tail join (O(M) concatenation).
 *
 *              Correctness invariant:
 *                Corpus is presorted alphabetically before sharding.
 *                Doc IDs are assigned as offset + local_index.
 *                Therefore all doc IDs in shard_i are strictly less
 *                than all doc IDs in shard_{i+1}. Concatenating
 *                shard results in shard order produces a globally
 *                sorted result — no comparison-based merge needed.
 *
 * @author Vedant Keshav Jadhav (vedantjadhav@arizona.edu)
 * @date April 2026
 *
 ***************************************************************/

#ifndef MASTER_ENGINE_HPP
#define MASTER_ENGINE_HPP

#include <string>
#include <vector>
#include <cstdint>

#include "preprocessor.hpp"
#include "boolean_engine.hpp"

#if PHASE == 3
#include <thread>
#include <mutex>
#include <condition_variable>
#include <future>
#endif

class MasterEngine {

    Preprocessor preprocessor;

    int n_shards;

    std::vector<BooleanEngine> engines;

    /* Const pointers into engines[i]::QueryRunner::q_result — zero copy */
    std::vector<const std::vector<uint32_t>*> shard_results;

#if PHASE == 3
    const std::vector<std::string> *current_query = nullptr;

    std::mutex              start_mtx;
    std::condition_variable start_cv;
    uint64_t                query_generation = 0;

    std::mutex              done_mtx;
    std::condition_variable done_cv;
    int                     done_count = 0;

    bool                    shutdown = false;

    std::vector<std::thread> workers;

    void worker_loop(int shard_id);
#endif

    std::vector<uint32_t> tail_join() const;

public:
    MasterEngine() = default;
    ~MasterEngine();

    /* n_shards: number of shard files (default 4).*/
    int init(const std::string &shard_dir,
             int  n_shards           = 4);

    std::vector<uint32_t> query(const std::string &raw_query);
};

#endif /* MASTER_ENGINE_HPP */
