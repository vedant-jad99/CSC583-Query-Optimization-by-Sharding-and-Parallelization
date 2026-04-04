#include <iostream>

#include "test_header.hpp"

int test_counter = 0;

int run_tests() {
	int test_tally_counter = 0;
	test_tally_counter += test_bin_reader();

	return test_tally_counter;
}

int main(int argc, char **argv) {
	int total_passed_tests = run_tests();
	std::cout<< total_passed_tests << " out of " << test_counter << " passed\n";

	return 0;
}
