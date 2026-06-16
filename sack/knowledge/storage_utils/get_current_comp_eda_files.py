import shutil
from pathlib import Path

from sack.knowledge.knowledge_config import SACKKnowledgeConfig


def copy_eda_files(current_comp: str) -> None:
    """Copy historical EDAInsight files into current-competition storage."""
    source_eda_path = Path(SACKKnowledgeConfig.history_edainsight_base_path)
    current_eda_path = Path(SACKKnowledgeConfig.current_comp_path)

    target_folders = ["pre_insight_extraction", "deep_insight_extraction"]
    file_name = "eda_insight.json"

    for folder in target_folders:
        source_file = source_eda_path / current_comp / folder / file_name
        target_file = current_eda_path / current_comp / folder / file_name

        if not source_file.is_file():
            raise FileNotFoundError(f"Source EDAInsight file does not exist: {source_file}")

        target_file.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_file, target_file)


if __name__ == "__main__":
    copy_eda_files("playground-series-s3e9")
