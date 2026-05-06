/****************************************************************
 *
 * @file master_engine.cpp
 * @description Phase 2/3 MasterEngine implementation.
 *
 *              Merge: O(M) tail join.
 *
 *              Because the corpus is presorted before sharding
 *              and doc IDs are assigned as offset + local_index,
 *              shard i owns doc IDs [i*shard_size, (i+1)*shard_size).
 *              These ranges are strictly ordered and non-overlapping.
 *              Shard result vectors are sorted internally by the
 *              Boolean engine. Concatenating them in shard order
 *              produces a globally sorted result with zero comparisons.
 *
 * @author Vedant Keshav Jadhav (vedantjadhav@arizona.edu)
 * @date April 2026
 *
 ***************************************************************/

#include <iostream>

#if PHASE == 3
#include <future>
#endif

#include "master_engine.hpp"

static std::string shard_path(const std::string &dir, int i) {
    std::string d = dir;
    if (!d.empty() && d.back() != '/') d += '/';
    return d + "shard_" + std::to_string(i) + ".bin";
}

MasterEngine::~MasterEngine() {
#if PHASE == 3
    {
        std::lock_guard<std::mutex> lock(start_mtx);
        shutdown = true;
        query_generation++;
    }
    start_cv.notify_all();
    for (auto &t : workers) {
        if (t.joinable()) t.join();
    }
#endif
}

int MasterEngine::init(const std::string &shard_dir,
                       int  n_shards_arg)
{
    n_shards = n_shards_arg;
    engines.resize(n_shards);
    shard_results.resize(n_shards, nullptr);

#if PHASE == 2
    std::cout << "Phase 2 engine: " << n_shards
              << " shards, merge: tail join, execution: sequential\n";

    for (int i = 0; i < n_shards; i++) {
        if (-1 == engines[i].init(shard_path(shard_dir, i)))
            return -1;
    }

#elif PHASE == 3
    std::cout << "Phase 3 engine: " << n_shards
              << " shards, merge: tail join, thread pool: persistent\n";

    std::vector<std::future<int>> futures;
    futures.reserve(n_shards);
    for (int i = 0; i < n_shards; i++) {
        const std::string path = shard_path(shard_dir, i);
        futures.push_back(
            std::async(std::launch::async, [this, i, path] {
                return engines[i].init(path);
            })
        );
    }
    for (auto &f : futures) {
        if (f.get() == -1) return -1;
    }

    /* Spawn persistent worker threads — one per shard */
    workers.reserve(n_shards);
    for (int i = 0; i < n_shards; i++)
        workers.emplace_back(&MasterEngine::worker_loop, this, i);
#endif

    return 0;
}

/* Phase 3: worker loop */
#if PHASE == 3
void MasterEngine::worker_loop(int shard_id) {
    uint64_t last_generation = 0;

    while (true) {
        /* Wait for new query or shutdown */
        {
            std::unique_lock<std::mutex> lock(start_mtx);
            start_cv.wait(lock, [&] {
                return query_generation > last_generation || shutdown;
            });
            if (shutdown) return;
            last_generation = query_generation;
        }
        /* Lock released — pure parallel execution */

        try {
            shard_results[shard_id] =
                &engines[shard_id].queryNormalized(*current_query);
        } catch (const std::exception &e) {
            std::cerr << "Worker " << shard_id << ": " << e.what();
            shard_results[shard_id] = nullptr;
        }

        { std::lock_guard<std::mutex> lock(done_mtx); done_count++; }
        done_cv.notify_one();
    }
}
#endif


std::vector<uint32_t> MasterEngine::query(const std::string &raw_query) {
    std::vector<std::string> normalized = preprocessor.process(raw_query);

#if PHASE == 2
    /* Sequential fan-out */
    for (int i = 0; i < n_shards; i++)
        shard_results[i] = &engines[i].queryNormalized(normalized);

#elif PHASE == 3
    /* Parallel fan-out via persistent thread pool */
    current_query = &normalized;

    { std::lock_guard<std::mutex> lock(done_mtx); done_count = 0; }
    { std::lock_guard<std::mutex> lock(start_mtx); query_generation++; }
    start_cv.notify_all();

    {
        std::unique_lock<std::mutex> lock(done_mtx);
        done_cv.wait(lock, [&] { return done_count == n_shards; });
    }

    current_query = nullptr;
#endif

    return tail_join();
}

std::vector<uint32_t> MasterEngine::tail_join() const {
    size_t total = 0;
    for (int i = 0; i < n_shards; i++)
        if (shard_results[i])
            total += shard_results[i]->size();

    std::vector<uint32_t> result;
    result.reserve(total);

    for (int i = 0; i < n_shards; i++) {
        if (shard_results[i])
            result.insert(result.end(),
                          shard_results[i]->cbegin(),
                          shard_results[i]->cend());
	}

    return result;
}
