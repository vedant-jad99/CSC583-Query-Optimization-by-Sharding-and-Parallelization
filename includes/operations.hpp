/****************************************************************
 *
 * @file operations.hpp
 * @description Boolean operation handler
 * @author Vedant Jadhav (vedantjadhav@arizona.edu)
 * @date April 5, 2026
 *
 ***************************************************************/

#ifndef OPERATION_HANDLER_HPP
#define OPERATION_HANDLER_HPP

#include <set>
#include <vector>
#include <cstdint>

typedef enum : int8_t {
    OP_NOT,
    OP_AND,
    OP_OR
} op_t;

class OperationHandler {
    const std::set<uint32_t> docIDs;

    std::vector<uint32_t> handle_not(const std::vector<uint32_t> &);
    std::vector<uint32_t> handle_and(const std::vector<uint32_t> &,
                                     const std::vector<uint32_t> &);
    std::vector<uint32_t> handle_or (const std::vector<uint32_t> &,
                                     const std::vector<uint32_t> &);

public:
    OperationHandler(std::set<uint32_t> docIds) : docIDs(std::move(docIds)) {}

    std::vector<uint32_t> handleOp(op_t, std::vector<std::vector<uint32_t>> &);
};

#endif /* OPERATION_HANDLER_HPP */
