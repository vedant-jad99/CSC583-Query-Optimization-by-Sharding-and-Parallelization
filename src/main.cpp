/****************************************************************
 *
 * @file main.cpp
 * @description Entry point for the Boolean query engine.
 *              Phase 1: uses BooleanEngine (single index).
 *              Phase 2: uses MasterEngine (sharded, sequential).
 *              Phase 3: uses MasterEngine (sharded, parallel).
 *
 * Usage:
 *   Phase 1:
 *     ./run_engine <index.bin> [--interactive | --bench-init | --bench]
 *
 *   Phase 2/3:
 *     ./run_engine <shards/> [--interactive | --bench-init | --bench]
 *                 [--shards N]
 *
 * @author Vedant Jadhav (vedantjadhav@arizona.edu)
 * @date April 3, 2026
 *
 ***************************************************************/

#include <chrono>
#include <string>
#include <vector>
#include <cstdint>
#include <iostream>

#ifndef PHASE
#define PHASE 1
#endif

#if PHASE == 1
#include "boolean_engine.hpp"
using EngineType = BooleanEngine;
#else
#include "master_engine.hpp"
using EngineType = MasterEngine;
#endif

/* ── CLI helpers ─────────────────────────────────────────────── */

static bool has_flag(int argc, char **argv, const std::string &flag) {
    for (int i = 1; i < argc; i++)
        if (std::string(argv[i]) == flag) return true;
    return false;
}

#if PHASE >= 2
static std::string get_flag(int argc, char **argv,
                             const std::string &flag,
                             const std::string &default_val = "") {
    for (int i = 1; i < argc - 1; i++)
        if (std::string(argv[i]) == flag) return argv[i + 1];
    return default_val;
}
#endif

/* ── Output helper ───────────────────────────────────────────── */

static void print_results(const std::vector<uint32_t> &results) {
    std::cout << "Results: [";
    if (results.empty()) { std::cout << "]\n\n"; return; }
    for (size_t i = 0; i < results.size(); i++) {
        std::cout << results[i];
        if (i < results.size() - 1) std::cout << ", ";
    }
    std::cout << "]\n\n";
}

/* ── Modes ───────────────────────────────────────────────────── */

static void run_interactive(EngineType &engine) {
    std::string query;
    while (true) {
        std::cout << "Query > ";
        if (!std::getline(std::cin, query)) break;
        if (query == "q" || query == "quit") break;
        if (query.empty()) continue;
        try {
            auto results = engine.query(query);
            print_results(results);
        } catch (const std::exception &e) {
            std::cerr << "Error: " << e.what();
        }
    }
}

static void run_bench(EngineType &engine) {
    std::cout << "READY\n";
    std::cout.flush();

    std::string query;
    while (std::getline(std::cin, query)) {
        if (query == "EXIT") break;
        if (query.empty()) continue;
        try {
            auto results = engine.query(query);
            for (size_t i = 0; i < results.size(); i++) {
                std::cout << results[i];
                if (i < results.size() - 1) std::cout << " ";
            }
            std::cout << "\n";
            std::cout.flush();
        } catch (const std::exception &e) {
            std::cerr << "Error: " << e.what();
            std::cout << "\n";
            std::cout.flush();
        }
    }
}

/* ── Entry point ─────────────────────────────────────────────── */

int main(int argc, char **argv) {
    if (argc < 2) {
        std::cerr << "Usage: " << argv[0]
                  << " <index_path>"
                  << " [--interactive | --bench-init | --bench]"
#if PHASE >= 2
                  << " [--shards N]"
#endif
                  << "\n";
        return 1;
    }

    const std::string index_path      = argv[1];
    const bool        bench_init_mode = has_flag(argc, argv, "--bench-init");
    const bool        bench_mode      = has_flag(argc, argv, "--bench");

    EngineType engine;
    int ret = -1;

#if PHASE == 1
    /* ── Phase 1: single index ──────────────────────────────── */

    if (bench_init_mode) {
        auto t0 = std::chrono::high_resolution_clock::now();
        ret = engine.init(index_path);
        auto t1 = std::chrono::high_resolution_clock::now();
        if (-1 == ret) return 1;
        double ms = std::chrono::duration<double, std::milli>(t1 - t0).count();
        std::cout << "INIT_TIME_MS: " << ms << "\n";
        return 0;
    }

    ret = engine.init(index_path);

#else
    /* ── Phase 2/3: sharded index ───────────────────────────── */

    const int n_shards = std::stoi(get_flag(argc, argv, "--shards", "4"));

    if (bench_init_mode) {
        auto t0 = std::chrono::high_resolution_clock::now();
        ret = engine.init(index_path, n_shards);
        auto t1 = std::chrono::high_resolution_clock::now();
        if (-1 == ret) return 1;
        double ms = std::chrono::duration<double, std::milli>(t1 - t0).count();
        std::cout << "INIT_TIME_MS: " << ms << "\n";
        return 0;
    }

    ret = engine.init(index_path, n_shards);

#endif

    if (-1 == ret) return 1;

    if (bench_mode)
        run_bench(engine);
    else
        run_interactive(engine);

    return 0;
}
