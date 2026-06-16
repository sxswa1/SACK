import argparse
import json
import logging
import os
import shutil
import sys
from pathlib import Path

from sack.paths import (
    SACK_CONFIG_PATH,
    SACK_STATUS_PATH,
    COMPETITION_DATA_DIR,
    EDA_COMPETITION_DATA_DIR,
    SACK_PACKAGE_DIR,
)


logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


class SACKPipelineError(RuntimeError):
    """Raised when the SACK workflow cannot complete."""


def copy_folder(src: str | Path, dst: str | Path) -> None:
    src = Path(src)
    dst = Path(dst)
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)
    logger.info("Copied directory %s -> %s", src, dst)


def copy_files_and_folders(src_base: str | Path, dst_base: str | Path, items: list[str]) -> None:
    src_base = Path(src_base)
    dst_base = Path(dst_base)
    dst_base.mkdir(parents=True, exist_ok=True)
    for item in items:
        src_path = src_base / item
        dst_path = dst_base / item
        if not src_path.exists():
            logger.warning("Source path does not exist, skipping: %s", src_path)
            continue
        if src_path.is_file():
            shutil.copy2(src_path, dst_path)
        else:
            if dst_path.exists():
                shutil.rmtree(dst_path)
            shutil.copytree(src_path, dst_path)


def run_eda_process(competition: str, eda_start_phase: str, config_path: str, max_retry: int = 3) -> bool:
    retry_count = 0
    while retry_count < max_retry:
        try:
            from sack.get_history_edainsight import get_competition_edainsight

            logger.info(
                "Running EDAInsight for %s from phase %s, attempt %s/%s",
                competition,
                eda_start_phase,
                retry_count + 1,
                max_retry,
            )
            eda_result = get_competition_edainsight(competition, eda_start_phase, use_mode="GetEDAInsight")
            if isinstance(eda_result, bool):
                eda_success = eda_result
            elif isinstance(eda_result, str):
                eda_success = eda_result.lower() == "success"
            else:
                eda_success = False

            if eda_success:
                logger.info("EDAInsight succeeded for %s", competition)
                return True

            retry_count += 1
            logger.warning("EDAInsight failed for %s; remaining retries: %s", competition, max_retry - retry_count)
        except Exception as exc:
            retry_count += 1
            logger.error("EDAInsight raised for %s: %s", competition, exc, exc_info=True)

    return False


def run_dspipeline_process(competition: str, dsp_start_phase: str, config_path: str) -> None:
    from sack.state import State
    from sack.sop import SOP

    logger.info("Running DSPipeline for %s from phase %s", competition, dsp_start_phase)

    sop = SOP(competition, use_mode="DSPipeline")
    new_state = State(phase=dsp_start_phase, competition=competition, use_mode="DSPipeline")

    root_logger = logging.getLogger()
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    root_logger.setLevel(logging.INFO)

    competition_comp_path = COMPETITION_DATA_DIR / competition
    competition_comp_path.mkdir(parents=True, exist_ok=True)
    file_handler = logging.FileHandler(competition_comp_path / f"{competition}.log", encoding="utf-8")
    console_handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)

    while True:
        exec_state_info, new_state = sop.step(state=new_state)
        if exec_state_info == "Fail":
            root_logger.error("DSPipeline failed; stopping.")
            raise SACKPipelineError(f"DSPipeline failed for {competition} at phase {new_state.phase if new_state else dsp_start_phase}.")
        if exec_state_info == "Complete":
            root_logger.info("DSPipeline completed for %s", competition)
            break


def _status_is_success(status) -> bool:
    if isinstance(status, bool):
        return status
    if isinstance(status, str):
        return status.lower() == "success"
    return False


def load_competition_status(status_file_path: str | Path) -> dict:
    status_file_path = Path(status_file_path)
    if not status_file_path.is_file():
        return {}
    try:
        with status_file_path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError:
        logger.error("Status file is invalid JSON: %s", status_file_path)
        return {}


def save_competition_status(status_file_path: str | Path, status_dict: dict) -> None:
    status_file_path = Path(status_file_path)
    status_file_path.parent.mkdir(parents=True, exist_ok=True)
    with status_file_path.open("w", encoding="utf-8") as f:
        json.dump(status_dict, f, indent=4, ensure_ascii=False)


def run_sack_pipeline(
    competition: str,
    eda_start_phase: str,
    dsp_start_phase: str,
    config_path: str,
    skip_eda: bool = False,
    force_eda: bool = False,
    working_dir: str | os.PathLike | None = None,
) -> None:
    runtime_dir = Path(working_dir or SACK_PACKAGE_DIR)

    try:
        competition_eda_path = EDA_COMPETITION_DATA_DIR / competition
        competition_comp_path = COMPETITION_DATA_DIR / competition

        if not competition_comp_path.exists():
            raise ValueError(f"Competition {competition} does not exist in {COMPETITION_DATA_DIR}.")

        eda_status_dict = load_competition_status(SACK_STATUS_PATH)
        eda_already_success = _status_is_success(eda_status_dict.get(competition, False))

        if skip_eda:
            if not eda_already_success:
                raise ValueError(f"Cannot skip EDAInsight generation: {competition} has no successful EDA status.")
            need_run_eda = False
        elif force_eda:
            need_run_eda = True
        else:
            need_run_eda = not eda_already_success

        eda_success = eda_already_success
        if need_run_eda:
            if not competition_eda_path.exists():
                copy_folder(competition_comp_path, competition_eda_path)
            eda_success = run_eda_process(competition, eda_start_phase, config_path, max_retry=3)
            eda_status_dict[competition] = "success" if eda_success else "fail"
            save_competition_status(SACK_STATUS_PATH, eda_status_dict)

        if eda_success:
            copy_files_and_folders(
                competition_eda_path,
                competition_comp_path,
                [
                    "train.csv",
                    "test.csv",
                    "sample_submission.csv",
                    "overview.txt",
                    "competition_info.txt",
                    "data_preparation",
                    "understand_background",
                ],
            )
        else:
            logger.error("EDAInsight failed for %s; starting DSPipeline from Data Preparation.", competition)
            dsp_start_phase = "Data Preparation"

        run_dspipeline_process(competition, dsp_start_phase, config_path)
    finally:
        logger.debug("SACK runtime directory resolved to %s", runtime_dir)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the unified SACK workflow for a competition.")
    parser.add_argument("--competition", default="playground-series-s5e10")
    parser.add_argument("--eda_start_phase", default="Data Preparation")
    parser.add_argument("--dsp_start_phase", default="Feature Engineering")
    parser.add_argument("--skip_eda", action="store_true")
    parser.add_argument("--force_eda", action="store_true")
    args = parser.parse_args()

    run_sack_pipeline(
        competition=args.competition,
        eda_start_phase=args.eda_start_phase,
        dsp_start_phase=args.dsp_start_phase,
        config_path=str(SACK_CONFIG_PATH),
        skip_eda=args.skip_eda,
        force_eda=args.force_eda,
        working_dir=SACK_PACKAGE_DIR,
    )
