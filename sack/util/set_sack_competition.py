from __future__ import annotations

from pathlib import Path
import sys


SACK_ROOT = Path(__file__).resolve().parents[2]
if str(SACK_ROOT) not in sys.path:
    sys.path.insert(0, str(SACK_ROOT))

from sack.knowledge.competition_loader import (  # noqa: E402
    copy_competition_files,
    copy_eda_files,
    load_current_competition,
)


def set_competition(competition_path: str, target_path: str) -> None:
    """Backward-compatible adapter for the integrated SACK knowledge loader."""
    load_current_competition(competition_path, target_path)
