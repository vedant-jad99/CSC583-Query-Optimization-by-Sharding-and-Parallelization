/****************************************************************
 *
 * @file ir_system.cpp
 * @description IR subsystem and QueryRunner implementation
 * @author Vedant Jadhav (vedantjadhav@arizona.edu)
 * @date April 5, 2026
 *
 ***************************************************************/

#include <stack>
#include <iostream>
#include <stdexcept>

#include "ir_system.hpp"

/*==============================================================
 * IR_System
 *==============================================================*/

IR_System::IR_System(
    std::unordered_map<std::string, std::vector<uint32_t>> index, std::set<uint32_t> docids)
	: handler(std::move(docids)), inverted_index(std::move(index)) {}

const std::vector<uint32_t> &IR_System::getPostingsList(const std::string &term) const {
    static const std::vector<uint32_t> empty {};
    auto it = inverted_index.find(term);
    return (it != inverted_index.end()) ? it->second : empty;
}

std::vector<uint32_t> IR_System::processQuery(const std::vector<std::string> &tokens) {
    std::stack<std::vector<uint32_t>> st;

    for (const std::string &token : tokens) {
        if (token[0] != '\\') {
            st.push(getPostingsList(token));
        } else {
            std::vector<std::vector<uint32_t>> operands;
            op_t op;

            if (token == "\\not") {
                if (st.empty()) {
                    throw std::runtime_error("NOT requires an operand but stack is empty.\n");
                }
                operands.push_back(st.top()); st.pop();
                op = OP_NOT;
            } else if (token == "\\and") {
                if (st.size() < 2) {
                    throw std::runtime_error("AND requires two operands but stack is insufficient.\n");
                }
                operands.push_back(st.top()); st.pop();
                operands.push_back(st.top()); st.pop();
                op = OP_AND;
            } else if (token == "\\or") {
                if (st.size() < 2) {
                    throw std::runtime_error("OR requires two operands but stack is insufficient.\n");
                }
                operands.push_back(st.top()); st.pop();
                operands.push_back(st.top()); st.pop();
                op = OP_OR;
            } else {
                std::cerr << "Illegal token: " << token << "\n";
                throw std::runtime_error("Illegal token in query.\n");
            }

            st.push(handler.handleOp(op, operands));
        }
    }

    if (st.size() != 1) {
        std::cerr << "Invalid query: unbalanced operands.\n";
        throw std::runtime_error("Invalid query.\n");
    }

    return st.top();
}

/*==============================================================
 * QueryRunner
 *==============================================================*/

int QueryRunner::initIRSystem( std::unordered_map<std::string, std::vector<uint32_t>> index, std::set<uint32_t> docids) {
    if (isInitDone || irs != nullptr) {
        std::cerr << "Error: Cannot re-initialize IR System.\n";
        return -1;
    }

    irs = std::make_unique<IR_System>(std::move(index), std::move(docids));
    isInitDone = true;
    return 0;
}

const std::vector<uint32_t> &QueryRunner::runQuery(const std::vector<std::string> &normalized_terms) {
	q_result = irs->processQuery(normalized_terms);
    return q_result;
}
