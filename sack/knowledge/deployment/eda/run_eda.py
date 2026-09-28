"""Single-case EDA entry point. Checks never instantiate/call paid models."""
from __future__ import annotations

import argparse
import importlib
import json
import re
from pathlib import Path
from urllib.parse import urlparse


def check_runtime(competition: str, require_credentials: bool) -> dict:
    from sack.paths import EDA_COMPETITION_DATA_DIR

    for module in (
        "pandas", "numpy", "scipy", "sklearn", "statsmodels", "matplotlib",
        "seaborn", "openai", "tiktoken", "sack.state", "sack.sop",
        "sack.Tools.eda_tools", "sack.Agents.eda_agent.eda_summarizer",
        "sack.Tools.retrieve_doc", "sack.Tools.unit_test", "sack.Tools.image_to_text",
        "sack.Tools.ml_tools", "sack.Tools.debug",
    ):
        importlib.import_module(module)
    from sack.get_history_edainsight import validate_runtime_sources
    validate_runtime_sources()

    import tempfile
    import chromadb
    from chromadb.config import Settings
    with tempfile.TemporaryDirectory(prefix="eda-chroma-check-") as temporary:
        database = chromadb.PersistentClient(path=temporary, settings=Settings(anonymized_telemetry=False))
        collection = database.get_or_create_collection("runtime-check")
        collection.add(ids=["one"], embeddings=[[0.1, 0.2]], documents=["offline test"])
        if collection.count() != 1:
            raise RuntimeError("Chroma offline read/write check failed")

    root = EDA_COMPETITION_DATA_DIR / competition
    raw = root / "rawdata"
    import pandas as pd
    files = {}
    for name in ("train.csv", "test.csv", "sample_submission.csv"):
        path = raw / name
        if not path.is_file():
            raise RuntimeError(f"Missing input: {path}")
        data = pd.read_csv(path)
        files[name] = {"rows": len(data), "columns": len(data.columns)}
    if not (raw / "overview.txt").is_file():
        raise RuntimeError("Missing rawdata/overview.txt")

    from sack.Tools.eda_tools import calculate_overall_missing_rate, analyze_numerical_skewness
    train = pd.read_csv(raw / "train.csv")
    missing_rate = calculate_overall_missing_rate(train)
    skewness = analyze_numerical_skewness(train)
    if not 0 <= missing_rate <= 1 or not isinstance(skewness, dict):
        raise RuntimeError("Offline EDA tool smoke check failed")
    from sack.sop import SOP
    from sack.state import State
    phases = SOP(competition, use_mode="GetEDAInsight").config["phases"]
    for phase in phases:
        State(phase=phase, competition=competition, use_mode="GetEDAInsight")

    from sack.api_handler import API_KEY_FILE, load_api_config
    ready = False
    if Path(API_KEY_FILE).is_file():
        key, *urls = load_api_config()
        ready = bool(key) and not key.startswith("REPLACE_") and all(
            url and urlparse(url).scheme == "https" and urlparse(url).netloc
            and not url.startswith("REPLACE_") for url in urls
        )
    if require_credentials and not ready:
        raise RuntimeError("API configuration missing/incomplete; edit the server credentials file")
    return {"runtime": "passed", "inputs": files, "credentials_ready": ready,
            "paid_model_called": False, "phase_count": len(phases),
            "offline_eda_tools": "passed", "train_missing_rate": missing_rate}


def validate_outputs(competition: str) -> dict:
    from sack.paths import EDA_COMPETITION_DATA_DIR

    reports = {}
    expected = {
        "pre_insight_extraction": {"data_quality", "basic_distribution", "basic_dimensionality"},
        "deep_insight_extraction": {"feature_relationships", "complexity", "special_scenarios"},
    }
    for phase, fields in expected.items():
        root = EDA_COMPETITION_DATA_DIR / competition / phase
        insight = json.loads((root / "eda_insight.json").read_text(encoding="utf-8"))
        validation = json.loads((root / "eda_insight_validation.json").read_text(encoding="utf-8"))
        if not isinstance(insight, dict) or not fields.issubset(insight):
            raise RuntimeError(f"Incomplete insight schema: {phase}")
        reports[phase] = {"insight": str(root / "eda_insight.json"), "validation": validation}
    return reports


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--competition", default="titanic")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--run", action="store_true", help="Explicitly allow paid model calls and generated code")
    parser.add_argument("--validate-results", action="store_true")
    args = parser.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,99}", args.competition):
        parser.error("competition must be a single safe directory name")
    if sum((args.check, args.run, args.validate_results)) != 1:
        parser.error("Select exactly one of --check, --run, --validate-results")
    if args.validate_results:
        print(json.dumps(validate_outputs(args.competition), ensure_ascii=False, indent=2))
        return
    print(json.dumps(check_runtime(args.competition, require_credentials=args.run), indent=2))
    if args.run:
        from sack.get_history_edainsight import get_competition_edainsight
        result = get_competition_edainsight(args.competition, start_phase="Data Preparation")
        if result != "success":
            raise RuntimeError("EDA workflow failed; inspect the competition log")
        print(json.dumps(validate_outputs(args.competition), ensure_ascii=False, indent=2))
        print("Files generated; inspect validation and unknown fields before accepting results.")


if __name__ == "__main__":
    main()
