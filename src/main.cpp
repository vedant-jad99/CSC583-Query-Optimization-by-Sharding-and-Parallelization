/****************************************************************
 *
 * @file main.cpp
 * @description Entry point for the Boolean query engine
 * @author Vedant Jadhav (vedantjadhav@arizona.edu)
 * @date April 3, 2026
 *
 ***************************************************************/

#include <chrono>
#include <string>
#include <vector>
#include <cstdint>
#include <iostream>

#include "boolean_engine.hpp"

static void print_results(const std::vector<uint32_t> &results) {
    std::cout << "Results: [";
    if (results.empty()) {
        std::cout << "]\n\n";
        return;
    }
    for (size_t i = 0; i < results.size(); i++) {
        std::cout << results[i];
        if (i < results.size() - 1) { std::cout << ", "; }
    }
    std::cout << "]\n\n";
}

static void run_interactive(BooleanEngine &engine) {
    std::string query;
    while (true) {
        std::cout << "Query > ";
        if (!std::getline(std::cin, query)) { break; }

        if (query == "q" || query == "quit") { break; }
        if (query.empty()) { continue; }

        try {
            auto results = engine.query(query);
            print_results(results);
        } catch (const std::exception &e) {
            std::cerr << "Error: " << e.what();
        }
    }
}

static void run_bench(BooleanEngine &engine) {
    /* Benchmark mode — reads queries from stdin, prints READY when init done */
    std::cout << "READY\n";
    std::cout.flush();

    std::string query;
    while (std::getline(std::cin, query)) {
        if (query == "EXIT") { break; }
        if (query.empty()) { continue; }

        try {
            auto results = engine.query(query);
            for (size_t i = 0; i < results.size(); i++) {
                std::cout << results[i];
                if (i < results.size() - 1) { std::cout << " "; }
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

int main(int argc, char **argv) {
    if (argc < 2) {
        std::cerr << "Usage: " << argv[0]
                  << " <index.bin> [--interactive | --bench-init | --bench]\n";
        return 1;
    }

    const std::string bin_path = argv[1];
    const std::string mode     = (argc >= 3) ? argv[2] : "--interactive";

    BooleanEngine engine;

    if (mode == "--bench-init") {
        /* Init only — print init time, exit */
        auto t0 = std::chrono::high_resolution_clock::now();
        int ret = engine.init(bin_path);
        auto t1 = std::chrono::high_resolution_clock::now();

        if (-1 == ret) { return 1; }

        double ms = std::chrono::duration<double, std::milli>(t1 - t0).count();
        std::cout << "INIT_TIME_MS: " << ms << "\n";
        return 0;
    }

    int ret = engine.init(bin_path);
    if (-1 == ret) { return 1; }

    if (mode == "--bench") {
        run_bench(engine);
    } else {
        run_interactive(engine);
    }

    return 0;
}
