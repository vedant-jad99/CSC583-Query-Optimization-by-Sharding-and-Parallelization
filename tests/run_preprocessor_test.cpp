#include <iostream>
#include "test_header.hpp"

int test_counter = 0;

int main() {
    int passed = test_preprocessor();
    std::cout << passed << " out of " << test_counter << " passed\n";
    return (passed == test_counter) ? 0 : 1;
}
