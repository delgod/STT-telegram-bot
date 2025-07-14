import sys
from pathlib import Path

# Add the project root directory to the Python path to allow tests to import
# the main application modules.
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root)) 