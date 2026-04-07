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
EXE=run_engine
TESTS=tests
SRC_FILES=$(filter-out $(SRCS)/main.cpp, $(wildcard $(SRCS)/*.cpp))
OBJ_FILES=$(patsubst $(SRCS)/%.cpp, $(OBJS)/%.o, $(SRC_FILES))
TEST_SRCS=$(TESTS)/*.cpp
TEST_EXE=run_test

VENV=scripts/.venv
PIP=$(VENV)/bin/pip
PYTHON=$(VENV)/bin/python
REQS=scripts/requirements.txt


all: index-builder cmple engine tests


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


engine: $(EXE)


$(EXE): $(OBJ_FILES)
	$(CC) $(CXXFLAGS) $(SRCS)/main.cpp $^ -o $@


$(OBJS)/%.o: $(SRCS)/%.cpp
	$(CC) $(CXXFLAGS) $^ -c -o $@


tests: $(TEST_EXE)


$(TEST_EXE): $(TEST_SRCS) $(OBJ_FILES)
	$(CC) $(CXXFLAGS) $^ -o $@


clean-venv:
	rm -rf $(VENV)


clean:
	rm -rf $(OBJS) $(TEST_EXE) $(EXE)


.PHONY: all index-builder clean-venv clean tests cmple mk_objs engine
