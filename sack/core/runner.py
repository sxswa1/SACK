from pathlib import Path

from sack.paths import SACK_CONFIG_PATH, SACK_PACKAGE_DIR, ensure_project_imports, ensure_runtime_dirs


def run_sack(
    competition: str,
    eda_start_phase: str = "Data Preparation",
    dsp_start_phase: str = "Preliminary Exploratory Data Analysis",
    skip_eda: bool = False,
    force_eda: bool = False,
) -> None:
    """Run the unified SACK workflow without changing the legacy phase logic."""
    ensure_project_imports()
    ensure_runtime_dirs()

    from sack import framework

    framework.run_sack_pipeline(
        competition=competition,
        eda_start_phase=eda_start_phase,
        dsp_start_phase=dsp_start_phase,
        config_path=str(SACK_CONFIG_PATH),
        skip_eda=skip_eda,
        force_eda=force_eda,
        working_dir=Path(SACK_PACKAGE_DIR),
    )
