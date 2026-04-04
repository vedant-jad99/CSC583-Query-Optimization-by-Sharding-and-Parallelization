##############################################################
#
# Project CSC583: Makefile to build the project.
# @author: Vedant Jadhav
# @date: April 3, 2026
#
##############################################################

VENV=scripts/.venv
PIP=$(VENV)/bin/pip
PYTHON=$(VENV)/bin/python
REQS=scripts/requirements.txt

all: index-builder

# Create virtual environment if does not already exists
$(VENV):
	python3 -m venv $(VENV)
	$(PIP) install -r $(REQS)

# The main index builder script
index-builder: $(VENV)
	echo "Python build here"

clean-venv:
	rm -rf $(VENV)


.PHONY: all index-builder clean-venv
