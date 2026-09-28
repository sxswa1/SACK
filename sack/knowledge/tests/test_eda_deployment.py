import json
import subprocess
import sys
from pathlib import Path

import pytest

from sack.knowledge.deployment.eda.run_eda import validate_outputs


@pytest.mark.parametrize("arguments", [[], ["--check", "--run"], ["--check", "--competition", "../outside"]])
def test_invalid_launch_options_rejected_before_runtime_import(arguments):
    script = Path(__file__).parents[1] / "deployment" / "eda" / "run_eda.py"
    result = subprocess.run([sys.executable, str(script), *arguments], capture_output=True, text=True)
    assert result.returncode == 2
    assert "usage:" in result.stderr


def test_unknown_validation_is_surfaced_not_silently_accepted(monkeypatch, tmp_path):
    import sack.paths
    monkeypatch.setattr(sack.paths, "EDA_COMPETITION_DATA_DIR", tmp_path)
    phases = {
        "pre_insight_extraction": ["data_quality", "basic_distribution", "basic_dimensionality"],
        "deep_insight_extraction": ["feature_relationships", "complexity", "special_scenarios"],
    }
    for phase, fields in phases.items():
        root = tmp_path / "titanic" / phase
        root.mkdir(parents=True)
        (root / "eda_insight.json").write_text(json.dumps({field: "unknown" for field in fields}))
        (root / "eda_insight_validation.json").write_text(json.dumps({"quality": "low"}))
    report = validate_outputs("titanic")
    assert len(report) == 2
    assert all(item["validation"]["quality"] == "low" for item in report.values())


def test_incomplete_insight_schema_rejected(monkeypatch, tmp_path):
    import sack.paths
    monkeypatch.setattr(sack.paths, "EDA_COMPETITION_DATA_DIR", tmp_path)
    root = tmp_path / "titanic" / "pre_insight_extraction"
    root.mkdir(parents=True)
    (root / "eda_insight.json").write_text("{}")
    (root / "eda_insight_validation.json").write_text("{}")
    with pytest.raises(RuntimeError, match="Incomplete insight schema"):
        validate_outputs("titanic")
