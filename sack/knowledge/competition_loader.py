import shutil
from pathlib import Path


def load_current_competition(source_competition_dir, target_competition_dir) -> Path:
    """Copy a competition workspace into SACKKnowledgeBase current-competition storage."""
    source = Path(source_competition_dir)
    target = Path(target_competition_dir)

    if not source.exists():
        raise FileNotFoundError(f"Competition source path does not exist: {source}")

    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(source, target)
    return target
