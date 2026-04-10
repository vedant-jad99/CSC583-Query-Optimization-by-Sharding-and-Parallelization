/****************************************************************
 *
 * @file operations.cpp
 * @description Boolean operation handler implementation
 * @author Vedant Jadhav (vedantjadhav@arizona.edu)
 * @date April 5, 2026
 *
 ***************************************************************/

#include <stdexcept>
#include "operations.hpp"

std::vector<uint32_t> OperationHandler::handleOp(op_t op, std::vector<std::vector<uint32_t>> &operands) {
    if (operands.size() > 2) {
        throw std::invalid_argument("Boolean queries require two or fewer operands.\n");
    }

    std::vector<uint32_t> result;

    switch (op) {
        case OP_NOT:
            if (operands.size() != 1) {
                throw std::invalid_argument("NOT requires exactly one operand.\n");
            }
            result = handle_not(operands[0]);
            break;
        case OP_AND:
            result = handle_and(operands[0], operands[1]);
            break;
        case OP_OR:
            result = handle_or(operands[0], operands[1]);
            break;
    }

    return result;
}

std::vector<uint32_t> OperationHandler::handle_not(const std::vector<uint32_t> &oper) {
    if (oper.empty()) {
        return std::vector<uint32_t>(docIDs.begin(), docIDs.end());
    }

    std::vector<uint32_t> result;
    size_t i = 0, s = oper.size();

    for (uint32_t id : docIDs) {
        if (i < s && id == oper[i]) {
            i++;
            continue;
        }
        result.push_back(id);
    }

    return result;
}

std::vector<uint32_t> OperationHandler::handle_and(const std::vector<uint32_t> &oper1, const std::vector<uint32_t> &oper2) {
    if (oper1.empty() || oper2.empty()) { return {}; }

    std::vector<uint32_t> result;
    size_t i = 0, j = 0;
    size_t s1 = oper1.size(), s2 = oper2.size();

    while (i < s1 && j < s2) {
        if (oper1[i] == oper2[j]) {
            result.push_back(oper1[i]);
            i++; j++;
        }
		else if (oper1[i] < oper2[j]) { i++; }
		else { j++; }
    }

    return result;
}

std::vector<uint32_t> OperationHandler::handle_or(const std::vector<uint32_t> &oper1, const std::vector<uint32_t> &oper2) {
    if (oper1.empty()) { return oper2; }
    if (oper2.empty()) { return oper1; }

    std::vector<uint32_t> result;
    size_t i = 0, j = 0;
    size_t s1 = oper1.size(), s2 = oper2.size();

    while (i < s1 || j < s2) {
        if (i < s1 && j < s2) {
            if (oper1[i] == oper2[j]) {
                result.push_back(oper1[i]);
                i++; j++;
            } else if (oper1[i] < oper2[j]) {
                result.push_back(oper1[i++]);
            } else {
                result.push_back(oper2[j++]);
            }
        } else if (i < s1) {
            result.push_back(oper1[i++]);
        } else {
            result.push_back(oper2[j++]);
        }
    }

    return result;
}
