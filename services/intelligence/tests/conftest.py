import sys
from pathlib import Path

# Make scripts/ importable from tests/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
# Make search-engine/src importable for test_search.py
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "search-engine"))
