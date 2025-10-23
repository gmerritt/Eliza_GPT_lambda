import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent

# Ensure project src directories are on sys.path for tests
sys.path.insert(0, str(ROOT / 'src'))
sys.path.insert(0, str(ROOT / 'Eliza-GPT' / 'src'))
