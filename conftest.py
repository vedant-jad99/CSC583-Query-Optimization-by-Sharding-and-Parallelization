import sys
import os

# Add pipeline/ to sys.path so bare imports (from file_reader import FileReader)
# resolve correctly when running pytest from the project root.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "pipeline"))
