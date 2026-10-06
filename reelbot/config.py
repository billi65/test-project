import json
import os
from pathlib import Path

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
HISTORY_PATH = ROOT / "history.json"


def load_config(path: Path | None = None) -> dict:
    load_dotenv(ROOT / ".env")
    with open(path or ROOT / "config.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def env(name: str, required: bool = True) -> str | None:
    value = os.environ.get(name)
    if required and not value:
        raise SystemExit(f"Missing {name}. Copy .env.example to .env and fill it in.")
    return value


def load_history() -> dict:
    if HISTORY_PATH.exists():
        return json.loads(HISTORY_PATH.read_text(encoding="utf-8"))
    return {"topics": []}


def save_history(history: dict) -> None:
    HISTORY_PATH.write_text(json.dumps(history, indent=2, ensure_ascii=False), encoding="utf-8")
