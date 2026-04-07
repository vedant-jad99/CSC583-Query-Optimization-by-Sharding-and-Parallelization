/****************************************************************
 *
 * @file preprocessor.cpp
 * @description Dummy preprocessor implementation
 * @author Vedant Jadhav (vedantjadhav@arizona.edu)
 * @date April 3, 2026
 *
 ***************************************************************/

#include "preprocessor.hpp"

// Stub function. For now, just tokenize based on white-spaces
std::vector<std::string> Preprocessor::process(const std::string &raw_query) {
    std::vector<std::string> tokens;
    size_t s_pos = 0;
    size_t f_pos = raw_query.find(' ', s_pos);

    while (f_pos != std::string::npos) {
        if (f_pos > s_pos) {
            tokens.push_back(raw_query.substr(s_pos, f_pos - s_pos));
        }
        s_pos = f_pos + 1;
        f_pos = raw_query.find(' ', s_pos);
    }

    if (s_pos < raw_query.size()) {
        tokens.push_back(raw_query.substr(s_pos));
    }

    return tokens;
}
