import argparse
import py_compile
import json
import logging
import multiprocessing as mp
import os
import sys
from pathlib import Path

from sack.paths import SACK_CONFIG_PATH, SACK_STATUS_PATH, EDA_COMPETITION_DATA_DIR


def validate_runtime_sources() -> None:
    source_paths = [
        Path(__file__).resolve().parent / "Tools" / "eda_tools.py",
    ]
    for source_path in source_paths:
        try:
            py_compile.compile(str(source_path), doraise=True)
        except py_compile.PyCompileError as exc:
            raise RuntimeError(f"Runtime source validation failed for {source_path}: {exc.msg}") from exc


def summarize_failure_log(competition_name: str, max_lines: int = 20) -> str:
    log_path = EDA_COMPETITION_DATA_DIR / competition_name / f"{competition_name}.log"
    if not log_path.is_file():
        return f"{log_path}: log file not found."

    try:
        lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError as exc:
        return f"{log_path}: failed to read log: {exc}"

    interesting = [
        line for line in lines
        if "ERROR" in line or "Traceback" in line or "Exception" in line or " failed" in line or " raised:" in line
    ]
    tail = interesting[-max_lines:] if interesting else lines[-max_lines:]
    return f"{log_path}:\n" + "\n".join(tail)


def load_competition_status(status_file_path: str | Path) -> dict:
    status_file_path = Path(status_file_path)
    if not status_file_path.is_file():
        return {}
    try:
        with status_file_path.open("r", encoding="utf-8") as f:
            status_dict = json.load(f)
        for comp, status in status_dict.items():
            if status not in ["success", "fail"]:
                status_dict[comp] = "fail"
        return status_dict
    except json.JSONDecodeError:
        logging.error("Status file is invalid JSON: %s", status_file_path)
        return {}


def save_competition_status(status_file_path: str | Path, status_dict: dict) -> None:
    status_file_path = Path(status_file_path)
    status_file_path.parent.mkdir(parents=True, exist_ok=True)
    with status_file_path.open("w", encoding="utf-8") as f:
        json.dump(status_dict, f, indent=4, ensure_ascii=False)


def get_competition_edainsight(
    competition_name: str,
    start_phase: str = "Data Preparation",
    use_mode: str = "GetEDAInsight",
) -> str:
    root_logger = logging.getLogger()
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    root_logger.setLevel(logging.INFO)

    log_file_dir = EDA_COMPETITION_DATA_DIR / competition_name
    log_file_dir.mkdir(parents=True, exist_ok=True)
    file_handler = logging.FileHandler(log_file_dir / f"{competition_name}.log", mode="w", encoding="utf-8")
    console_handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)

    try:
        from sack.state import State
        from sack.sop import SOP

        root_logger.info("Start EDAInsight for %s from phase %s", competition_name, start_phase)
        sop = SOP(competition_name, use_mode=use_mode)
        new_state = State(phase=start_phase, competition=competition_name, use_mode=use_mode)

        while True:
            previous_state = new_state
            exec_state_info, new_state = sop.step(state=new_state)
            if exec_state_info == "Fail":
                failed_state = new_state or previous_state
                logging.error("%s failed at phase=%s score=%s", competition_name, failed_state.phase, failed_state.score)
                return "fail"
            if exec_state_info == "Complete":
                logging.info("%s completed", competition_name)
                return "success"
    except Exception as exc:
        logging.error("%s raised: %s", competition_name, exc, exc_info=True)
        return "fail"
    finally:
        for handler in root_logger.handlers[:]:
            root_logger.removeHandler(handler)


def process_competition_simple(comp_name: str, start_phase: str) -> tuple[str, str]:
    try:
        result = get_competition_edainsight(comp_name, start_phase)
        return comp_name, result
    except Exception as exc:
        log_file_dir = EDA_COMPETITION_DATA_DIR / comp_name
        log_file_dir.mkdir(parents=True, exist_ok=True)
        fallback_log = log_file_dir / f"{comp_name}.log"
        logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
        with fallback_log.open("w", encoding="utf-8") as f:
            f.write(f"{comp_name} failed before normal logging was initialized.\n")
            f.write(f"{type(exc).__name__}: {exc}\n")
        logging.exception("%s failed before normal logging was initialized", comp_name)
        return comp_name, "fail"


def main() -> None:
    if sys.platform == "win32":
        mp.set_start_method("spawn", force=True)

    parser = argparse.ArgumentParser(description="Run EDAInsight generation for pending competitions.")
    parser.add_argument("--start-phase", default="Data Preparation")
    parser.add_argument("--pool-size", type=int, default=min(mp.cpu_count(), 4))
    args = parser.parse_args()
    validate_runtime_sources()

    status_file_path = str(SACK_STATUS_PATH)
    comp_status_dict = load_competition_status(status_file_path)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
    if not EDA_COMPETITION_DATA_DIR.exists():
        logging.warning("EDA competition data directory does not exist: %s", EDA_COMPETITION_DATA_DIR)
        return

    pending_comps = []
    for hist_comp in os.listdir(EDA_COMPETITION_DATA_DIR):
        hist_comp_path = EDA_COMPETITION_DATA_DIR / hist_comp
        if hist_comp_path.is_dir() and comp_status_dict.get(hist_comp) != "success":
            pending_comps.append(hist_comp)

    if not pending_comps:
        logging.info("No pending competitions.")
        return

    pool = mp.Pool(processes=args.pool_size)
    async_results = []
    try:
        for comp_name in pending_comps:
            async_results.append(pool.apply_async(
                process_competition_simple,
                args=(comp_name, args.start_phase),
            ))
        pool.close()
        pool.join()
    except KeyboardInterrupt:
        pool.terminate()
        pool.join()
        raise

    result_dict = {}
    for async_result in async_results:
        comp_name, result = async_result.get()
        result_dict[comp_name] = result
        comp_status_dict[comp_name] = result
    save_competition_status(status_file_path, comp_status_dict)
    processed_count = len(result_dict)
    successes_count = sum(1 for value in result_dict.values() if value == "success")
    print(f"Processed: {processed_count}; success: {successes_count}; fail: {processed_count - successes_count}")
    failed_comps = [name for name, value in result_dict.items() if value != "success"]
    if failed_comps:
        print("\nFailure summary:")
        for comp_name in failed_comps[:10]:
            print(summarize_failure_log(comp_name))
            print("-" * 80)
        if len(failed_comps) > 10:
            print(f"... {len(failed_comps) - 10} more failed competitions omitted. Check their logs under {EDA_COMPETITION_DATA_DIR}.")


if __name__ == "__main__":
    main()
