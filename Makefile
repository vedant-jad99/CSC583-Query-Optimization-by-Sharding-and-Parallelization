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
	$(PYTHON) scripts/main.py --corpus data/corpus --out index.bin
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


BENCH_PHASE ?= 1

bench-indexing:
	$(PYTHON) benchmark/bench_indexing.py \
		--corpus     data/corpus \
		--pipeline   scripts/main.py \
		--output     bench.bin \
		--runs       5 \
		--phase      $(BENCH_PHASE) \
		--output-dir benchmark/results \
		--python     $(PYTHON)

bench-init:
	$(PYTHON) benchmark/bench_init.py \
		--engine ./run_engine \
		--index  index.bin \
		--runs   20 \
		--phase  $(BENCH_PHASE) \
		--output-dir benchmark/results

bench-query:
	$(PYTHON) benchmark/bench_query.py \
		--engine     ./run_engine \
		--index      index.bin \
		--queries    benchmark/queries \
		--warmup     10 \
		--runs       50 \
		--phase      $(BENCH_PHASE) \
		--output-dir benchmark/results

bench-memory:
	bash benchmark/bench_memory.sh \
		./run_engine index.bin \
		benchmark/results/phase$(BENCH_PHASE)/memory.jsonl \
		$(BENCH_PHASE)

bench-report:
	$(PYTHON) benchmark/report.py \
		--results-dir benchmark/results \
		--phases      $(BENCH_PHASE) \
		--output-dir  benchmark/results/plots


bench: bench-indexing bench-init bench-query bench-memory bench-report


tests: $(TEST_EXE)


$(TEST_EXE): $(TEST_SRCS) $(OBJ_FILES)
	$(CC) $(CXXFLAGS) $^ -o $@


clean-venv:
	rm -rf $(VENV)


clean:
	rm -rf $(OBJS) $(TEST_EXE) $(EXE) index.bin


.PHONY: all index-builder clean-venv clean tests cmple mk_objs engine bench bench-init bench-query bench-memory bench-report
