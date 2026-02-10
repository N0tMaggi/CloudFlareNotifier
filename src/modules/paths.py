from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[2]
STATE_FILE = BASE_DIR / "state.json"
LOG_DIR = BASE_DIR / "logs"
ENV_FILE = BASE_DIR / ".env"
