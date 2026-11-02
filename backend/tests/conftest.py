import os
import sys
from pathlib import Path

# Tests are deterministic: no network, no LLM.
os.environ['MOODFLIX_OFFLINE'] = '1'
os.environ.pop('OPENAI_API_KEY', None)
os.environ.pop('TMDB_API_KEY', None)
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
