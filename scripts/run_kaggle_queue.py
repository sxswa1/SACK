"""Run an explicitly prepared SACK manifest sequentially and preserve evidence.

Usage: python run_kaggle_queue.py /absolute/path/manifest.json
Each entry supplies a private working copy and its sack-python entry point.
The queue never submits predictions to Kaggle and never retries paid runs.
"""

import datetime as dt
import fcntl
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def save(path, value):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")
    temporary.replace(path)


def digest(path):
    result = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            result.update(chunk)
    return result.hexdigest()


def validate(entry, returncode):
    """Validate real outputs separately from the subprocess exit status."""
    import numpy as np
    import pandas as pd

    errors = []
    repo = Path(entry["repo"])
    comp = entry["competition"]
    workspace = repo / "data/competitions" / comp
    evidence = {"checked_at": now(), "exit_code": returncode, "errors": errors}
    try:
        sys.path.insert(0, str(repo))
        from sack.model_audit import validate_receipt
        model_stage = workspace / 'model_build_predict'
        evidence['training_evidence'] = validate_receipt(
            workspace, model_stage / 'model_build_predict_run_code.py',
            model_stage / 'training_execution.json')
    except (OSError, ValueError, KeyError) as exc:
        errors.append('Real training/prediction evidence: ' + str(exc))
    for name, expected in entry["raw_sha256"].items():
        if digest(workspace / "rawdata" / name) != expected:
            errors.append("Raw input changed: " + name)
    if returncode != 0:
        errors.append("Pipeline did not exit successfully")
    log = Path(entry["log"]).read_text(errors="replace")
    if f"DSPipeline completed for {comp}" not in log:
        errors.append("DSP completion message missing")
    status = json.loads((repo / "sack/competition_process_status.json").read_text())
    evidence["eda_status"] = status.get(comp)
    if status.get(comp) != "success":
        errors.append("Independent EDA did not succeed")
    for phase in ("pre_insight_extraction", "deep_insight_extraction"):
        folder = repo / "data/eda_competitions" / comp / phase
        try:
            insight = json.loads((folder / "eda_insight.json").read_text())
            def check(value):
                if isinstance(value, dict):
                    return all(check(v) for v in value.values())
                if isinstance(value, list):
                    return all(check(v) for v in value)
                if value is None:
                    return False
                if isinstance(value, str) and value.strip().lower() in {"unknown", "none", "nan"}:
                    return False
                return not isinstance(value, float) or bool(np.isfinite(value))
            if not check(insight):
                errors.append(phase + ": incomplete or nonfinite insight")
            quality = json.loads((folder / "eda_insight_validation.json").read_text())
            evidence[phase] = quality
            for key in ("unknown_fields_count", "missing_schema_fields"):
                if key not in quality or quality[key]:
                    errors.append(phase + ": " + key + " missing or nonzero")
            tools = quality.get("tool_output_validation", {})
            if "missing_tool_outputs" not in tools or tools["missing_tool_outputs"]:
                errors.append(phase + ": missing tool outputs")
        except (OSError, ValueError) as exc:
            errors.append(phase + ": " + str(exc))
    try:
        original_train = pd.read_csv(workspace / "rawdata/train.csv")
        original_test = pd.read_csv(workspace / "rawdata/test.csv")
        for prefix in ("cleaned", "processed"):
            train = pd.read_csv(workspace / f"{prefix}_train.csv")
            test = pd.read_csv(workspace / f"{prefix}_test.csv")
            if len(train) != len(original_train) or len(test) != len(original_test):
                errors.append(prefix + ": row counts changed")
            targets = set(train.columns) - set(test.columns)
            if not targets or not (set(train.columns) - targets) == set(test.columns):
                errors.append(prefix + ": predictor columns do not align")
        sample = pd.read_csv(workspace / "sample_submission.csv", dtype=str)
        submission = pd.read_csv(workspace / "submission.csv", dtype=str)
        if list(sample.columns) != list(submission.columns) or len(sample) != len(submission):
            errors.append("Submission schema or row count mismatch")
        elif sample.iloc[:, 0].tolist() != submission.iloc[:, 0].tolist():
            errors.append("Submission IDs or ordering changed")
        if submission.isna().any().any():
            errors.append("Submission contains missing values")
        raw_sample = pd.read_csv(workspace / "rawdata/sample_submission.csv", dtype=str)
        evidence["original_kaggle_schema_matches"] = list(raw_sample.columns) == list(submission.columns)
        if len(raw_sample) != len(submission) or raw_sample.iloc[:, 0].tolist() != submission.iloc[:, 0].tolist():
            errors.append("Submission does not preserve original Kaggle IDs")
        # These prepared tasks require categorical predictions, not probabilities.
        for index in range(1, len(submission.columns)):
            target = raw_sample.columns[index]
            allowed = set(original_train[target].dropna().astype(str))
            if not set(submission.iloc[:, index]).issubset(allowed):
                errors.append("Prediction labels outside training classes: " + target)
        evidence["submission_rows"] = len(submission)
        evidence["submission_sha256"] = digest(workspace / "submission.csv")
    except (OSError, ValueError, KeyError, IndexError) as exc:
        errors.append("Output validation: " + str(exc))
    evidence["accepted"] = not errors
    return evidence


def run(manifest_path):
    manifest_path = Path(manifest_path).resolve()
    root = manifest_path.parent
    manifest = json.loads(manifest_path.read_text())
    with (root / "queue.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        # An accidental service restart must never silently replay paid requests.
        with (root / "started.json").open("x") as marker:
            json.dump({"started_at": now(), "pid": os.getpid()}, marker)
        state = {"started_at": now(), "status": "running", "experiments": []}
        for entry in manifest["experiments"]:
            state["experiments"].append({"competition": entry["competition"], "status": "pending"})
        save(root / "status.json", state)
        for entry, item in zip(manifest["experiments"], state["experiments"]):
            item.update(status="running", started_at=now(), log=entry["log"])
            save(root / "status.json", state)
            command = [entry["python"], "-u", "-m", "sack", "run", "--competition",
                       entry["competition"], "--skip-eda" if entry.get("skip_eda") else "--force-eda",
                       "--eda-start-phase", entry.get("eda_start_phase", "Data Preparation"),
                       "--dsp-start-phase", entry.get("dsp_start_phase", "Data Preparation")]
            timed_out = False
            start = time.monotonic()
            with open(entry["log"], "xb", buffering=0) as output:
                process = subprocess.Popen(command, stdout=output, stderr=subprocess.STDOUT,
                                           cwd=entry["repo"], start_new_session=True)
                item["pid"] = process.pid
                save(root / "status.json", state)
                try:
                    returncode = process.wait(timeout=entry.get("timeout_seconds", 43200))
                except subprocess.TimeoutExpired:
                    timed_out = True
                    os.killpg(process.pid, signal.SIGTERM)
                    try:
                        process.wait(timeout=30)
                    except subprocess.TimeoutExpired:
                        os.killpg(process.pid, signal.SIGKILL)
                        process.wait()
                    returncode = 124
                finally:
                    # Generated tools can leave descendants; finish cleanup before
                    # the next competition begins, even after a normal parent exit.
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
            try:
                acceptance = validate(entry, returncode)
            except Exception as exc:
                acceptance = {"accepted": False, "errors": ["Validator failed: " + repr(exc)]}
            save(Path(entry["acceptance"]), acceptance)
            item.update(status="succeeded" if acceptance["accepted"] else "failed",
                        ended_at=now(), elapsed_seconds=round(time.monotonic() - start, 1),
                        exit_code=returncode, timed_out=timed_out, acceptance=entry["acceptance"])
            save(root / "status.json", state)
        state.update(status="finished", ended_at=now())
        save(root / "status.json", state)
        return int(any(item["status"] != "succeeded" for item in state["experiments"]))


if __name__ == "__main__":
    sys.exit(run(sys.argv[1]))
