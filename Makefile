##############################################################
#
# Project CSC583: Makefile to build the project.
# @author: Vedant Jadhav
# @date: April 3, 2026
#
##############################################################

CC=g++
INC_FLAGS=-Iincludes
CXXFLAGS=-Wall -Wextra -std=c++17 $(INC_FLAGS)

SRCS=src
OBJS=obj
TESTS=tests
OBJ_FILES=$(patsubst $(SRCS)/%.cpp, $(OBJS)/%.o, $(wildcard $(SRCS)/*.cpp))
TEST_SRCS=$(TESTS)/*.cpp
TEST_EXE=run_test

VENV=scripts/.venv
PIP=$(VENV)/bin/pip
PYTHON=$(VENV)/bin/python
REQS=scripts/requirements.txt


all: index-builder cmple tests


#==============================================================================
# = Index building script. Should run at compile time and build static index. =
#==============================================================================
# Create virtual environment if does not already exists
$(VENV):
	python3 -m venv $(VENV)
	$(PIP) install -r $(REQS)

# The main index builder script
index-builder: $(VENV)
	echo "Python build here"
#==============================================================================


mk_objs:
	mkdir -p $(OBJS)


cmple: mk_objs $(OBJ_FILES)


$(OBJS)/%.o: $(SRCS)/%.cpp
	$(CC) $(CXXFLAGS) $^ -c -o $@


tests: $(TEST_EXE)


$(TEST_EXE): $(TEST_SRCS) $(OBJ_FILES)
	$(CC) $(CXXFLAGS) $^ -o $@


clean:
	rm -rf $(OBJS) run_tests


clean-venv:
	rm -rf $(VENV)


.PHONY: all index-builder clean-venv clean tests cmple mk_objs
