/****************************************************************
 *
 * @file preprocessor.hpp
 * @description Dummy preprocessor — full implementation deferred
 * @author Vedant Jadhav (vedantjadhav@arizona.edu), Arun Sanyal
 * @date April 5, 2026
 *
 ***************************************************************/

#ifndef PREPROCESSOR_HPP
#define PREPROCESSOR_HPP

#include <string>
#include <vector>

class Preprocessor {
public:
    /* Run the preprocessing steps on the query */
    std::vector<std::string> process(const std::string &raw_query);
};

#endif /* PREPROCESSOR_HPP */
