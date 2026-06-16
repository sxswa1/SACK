import os
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
SACK_PACKAGE_DIR = PROJECT_ROOT / "sack"

COMPETITION_DATA_DIR = PROJECT_ROOT / "data" / "competitions"
EDA_COMPETITION_DATA_DIR = PROJECT_ROOT / "data" / "eda_competitions"

SACK_KNOWLEDGE_STORAGE_DIR = PROJECT_ROOT / "storage"
HISTORICAL_CASE_DIR = EDA_COMPETITION_DATA_DIR
SACK_KNOWLEDGE_DATA_SOURCE_DIR = HISTORICAL_CASE_DIR
SACK_KNOWLEDGE_CURRENT_COMP_DIR = SACK_KNOWLEDGE_STORAGE_DIR / "current_comp" / "kaggle"

SACK_CONFIG_PATH = SACK_PACKAGE_DIR / "config.json"
SACK_STATUS_PATH = SACK_PACKAGE_DIR / "competition_process_status.json"


def env_path(name: str, default: Path) -> str:
    return str(Path(os.environ.get(name, default)).expanduser().resolve())


def ensure_project_imports() -> None:
    """Expose legacy modules while the unified SACK package owns orchestration."""
    paths = [
        PROJECT_ROOT,
        SACK_PACKAGE_DIR,
        SACK_PACKAGE_DIR / "Agents",
        SACK_PACKAGE_DIR / "Prompts",
        SACK_PACKAGE_DIR / "Tools",
        SACK_PACKAGE_DIR / "LLMComponent",
        SACK_PACKAGE_DIR / "knowledge",
    ]
    for path in reversed(paths):
        path_str = str(path)
        if path_str not in sys.path:
            sys.path.insert(0, path_str)


def ensure_runtime_dirs() -> None:
    for path in (COMPETITION_DATA_DIR, EDA_COMPETITION_DATA_DIR, SACK_KNOWLEDGE_CURRENT_COMP_DIR):
        path.mkdir(parents=True, exist_ok=True)
