"""Run the ShopSphere data pipeline and optionally open its Streamlit dashboard.

From this project folder, run:
    python run_project_pipeline.py

This first rebuilds the cleaned silver data and KPI CSV outputs via 04_pipeline.py,
then starts overview_dashboard.py. Raw source files are not modified.
"""
import argparse
from pathlib import Path
import subprocess
import sys

BASE = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(
        description="Run the complete ShopSphere pipeline and dashboard."
    )
    parser.add_argument(
        "--skip-clean",
        action="store_true",
        help="Reuse the existing silver database and only rebuild KPI outputs.",
    )
    parser.add_argument(
        "--no-dashboard",
        action="store_true",
        help="Run cleaning, checks, and KPI exports without opening Streamlit.",
    )
    args = parser.parse_args()

    pipeline_command = [sys.executable, str(BASE / "04_pipeline.py")]
    if args.skip_clean:
        pipeline_command.append("--skip-clean")

    print("Starting data preparation and KPI pipeline...")
    pipeline_result = subprocess.run(pipeline_command, cwd=BASE)
    if pipeline_result.returncode != 0:
        raise SystemExit(pipeline_result.returncode)

    if args.no_dashboard:
        print("Pipeline finished. Dashboard was not started (--no-dashboard).")
        return

    print("Starting the Streamlit dashboard...")
    dashboard_command = [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        str(BASE / "overview_dashboard.py"),
    ]
    dashboard_result = subprocess.run(dashboard_command, cwd=BASE)
    if dashboard_result.returncode != 0:
        raise SystemExit(dashboard_result.returncode)


if __name__ == "__main__":
    main()
