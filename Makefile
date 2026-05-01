##############################################################
#
# Project CSC583: Makefile to build the project.
# @author: Vedant Jadhav
# @date: April 3, 2026
#
##############################################################

CC       = g++
PHASE   ?= 1
INC_FLAGS = -Iincludes
CXXFLAGS  = -Wall -Wextra -std=c++17 -DPHASE=$(PHASE) $(INC_FLAGS)

ifeq ($(PHASE), 3)
CXXFLAGS += -pthread
endif

SRCS     = src
OBJS     = obj
SHARDS   = shards
EXE      = run_engine
TESTS    = tests
TEST_EXE = run_test

# Phase 1: exclude master_engine.cpp (not needed)
# Phase 2/3: exclude nothing — both boolean_engine.cpp and master_engine.cpp compile
ifeq ($(PHASE), 1)
EXCLUDE = $(SRCS)/master_engine.cpp
else
EXCLUDE =
endif

# Always exclude main.cpp (linked separately)
EXCLUDE += $(SRCS)/main.cpp
SRC_FILES = $(filter-out $(EXCLUDE), $(wildcard $(SRCS)/*.cpp))
OBJ_FILES = $(patsubst $(SRCS)/%.cpp, $(OBJS)/%.o, $(SRC_FILES))
TEST_SRCS = $(TESTS)/*.cpp

VENV   = scripts/.venv
PIP    = $(VENV)/bin/pip
PYTHON = $(VENV)/bin/python3
REQS   = scripts/requirements.txt

# Benchmark configuration
BENCH_PHASE    ?= 1
N_SHARDS       ?= 4


all: index-builder cmple engine tests


#==============================================================================
# Index building
#==============================================================================
$(VENV):
	python3 -m venv $(VENV)
	$(PIP) install -r $(REQS)

index-builder: $(VENV)
ifeq ($(PHASE), 1)
	$(PYTHON) scripts/main.py --corpus data.nosync/$(CORPUS) --out index.bin
else
	$(PYTHON) scripts/main_sharded.py --corpus data.nosync/$(CORPUS) --out-dir $(SHARDS)/
endif
#==============================================================================


mk_objs:
	mkdir -p $(OBJS)


cmple: mk_objs $(OBJ_FILES)


engine: $(EXE)


$(EXE): $(OBJ_FILES)
	$(CC) $(CXXFLAGS) $(SRCS)/main.cpp $^ -o $@


$(OBJS)/%.o: $(SRCS)/%.cpp
	$(CC) $(CXXFLAGS) $^ -c -o $@


#==============================================================================
# Benchmarking
#
# Usage:
#   make bench BENCH_PHASE=1
#   make bench BENCH_PHASE=2 N_SHARDS=4 
#   make bench-report BENCH_PHASE="1 2 3"
#==============================================================================

bench-indexing:
ifeq ($(BENCH_PHASE), 1)
	$(PYTHON) benchmark/bench_indexing.py \
		--corpus     data.nosync/$(CORPUS) \
		--pipeline   scripts/main.py \
		--output     bench.bin \
		--runs       5 \
		--phase      $(BENCH_PHASE) \
		--output-dir benchmark/results \
		--python     $(PYTHON)
else
	$(PYTHON) benchmark/bench_indexing.py \
		--corpus     data.nosync/$(CORPUS) \
		--pipeline   scripts/main_sharded.py \
		--output     bench-shards \
		--runs       5 \
		--phase      $(BENCH_PHASE) \
		--output-dir benchmark/results \
		--python     $(PYTHON)
endif

bench-init:
ifeq ($(BENCH_PHASE), 1)
	$(PYTHON) benchmark/bench_init.py \
		--engine     ./$(EXE) \
		--index      bench.bin \
		--runs       20 \
		--phase      $(BENCH_PHASE) \
		--output-dir benchmark/results
else
	$(PYTHON) benchmark/bench_init.py \
		--engine          ./$(EXE) \
		--index           bench-shards/ \
		--runs            20 \
		--phase           $(BENCH_PHASE) \
		--output-dir      benchmark/results \
		--shards          $(N_SHARDS)
endif

bench-query:
ifeq ($(BENCH_PHASE), 1)
	$(PYTHON) benchmark/bench_query.py \
		--engine     ./$(EXE) \
		--index      bench.bin \
		--queries    benchmark/queries \
		--warmup     10 \
		--runs       50 \
		--phase      $(BENCH_PHASE) \
		--output-dir benchmark/results
else
	$(PYTHON) benchmark/bench_query.py \
		--engine          ./$(EXE) \
		--index           bench-shards/ \
		--queries         benchmark/queries \
		--warmup          10 \
		--runs            50 \
		--phase           $(BENCH_PHASE) \
		--output-dir      benchmark/results \
		--shards          $(N_SHARDS)
endif

bench-memory:
ifeq ($(BENCH_PHASE), 1)
	bash benchmark/bench_memory.sh \
		./$(EXE) bench.bin \
		benchmark/results/phase$(BENCH_PHASE)/memory.jsonl \
		$(BENCH_PHASE)
else
	bash benchmark/bench_memory.sh \
		./$(EXE) bench-shards/ \
		benchmark/results/phase$(BENCH_PHASE)/memory.jsonl \
		$(BENCH_PHASE) \
		--shards $(N_SHARDS)
endif

bench-report:
	$(PYTHON) benchmark/report.py \
		--results-dir benchmark/results \
		--phases      $(BENCH_PHASE) \
		--output-dir  benchmark/results/plots


bench: bench-indexing bench-init bench-query bench-memory bench-report


#==============================================================================
# Tests
#==============================================================================
tests: $(TEST_EXE)


$(TEST_EXE): $(TEST_SRCS) $(OBJ_FILES)
	$(CC) $(CXXFLAGS) $^ -o $@


clean:
	rm -rf $(OBJS) $(TEST_EXE) $(EXE) index.bin shards bench.bin bench-shards

clean-venv:
	rm -rf $(VENV)

clean-shards:
	rm -rf $(SHARDS)


.PHONY: all index-builder clean clean-venv clean-shards tests \
        cmple mk_objs engine \
        bench bench-indexing bench-init bench-query bench-memory bench-report
