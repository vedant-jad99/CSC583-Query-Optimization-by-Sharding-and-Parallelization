/****************************************************************
 *
 * @file ir_system.hpp
 * @description IR subsystem and QueryRunner
 * @author Vedant Jadhav (vedantjadhav@arizona.edu)
 * @date April 3, 2026
 *
 ***************************************************************/

#ifndef IR_SYSTEM_HPP
#define IR_SYSTEM_HPP

#include <set>
#include <string>
#include <vector>
#include <memory>
#include <cstdint>
#include <unordered_map>

#include "operations.hpp"

class IR_System {
    OperationHandler handler;

    const std::unordered_map<std::string, std::vector<uint32_t>> inverted_index;

    const std::vector<uint32_t> &getPostingsList(const std::string &) const;

public:
    IR_System(std::unordered_map<std::string, std::vector<uint32_t>>,
              std::set<uint32_t>);

    std::vector<uint32_t> processQuery(const std::vector<std::string> &);
};


class QueryRunner {
    bool isInitDone = false;

    std::unique_ptr<IR_System> irs;

    void parseQuery(const std::string &, std::vector<std::string> &);

	std::vector<uint32_t> q_result;

public:
    int initIRSystem(std::unordered_map<std::string, std::vector<uint32_t>>,
                     std::set<uint32_t>);

    const std::vector<uint32_t> &runQuery(const std::vector<std::string> &normalized_terms);
};

#endif /* IR_SYSTEM_HPP */
