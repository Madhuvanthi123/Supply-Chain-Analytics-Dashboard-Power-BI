"""Supply chain analytics pipeline — orchestrator with an interactive menu.

Run ``python main.py`` for a zero-setup demo, or use ``--mode mysql`` after
loading ``sql/schema.sql`` in MySQL Workbench 8.0 CE.

This file wires the three project modules together in order, then opens an
interactive menu so you can choose what to look at:

1. Open raw data
2. Open Power BI dashboard
3. Python analysis (KPI summary)
4. Charts

Modules used:
- database_connection.py — gets the data (MySQL, or reproducible demo data)
- analysis.py             — enriches the data and calculates KPIs/exports
- visualizations.py        — draws the matplotlib/seaborn charts
"""

from __future__ import annotations

import argparse
import logging
import os
import subprocess
import sys
from pathlib import Path

import pandas as pd

from analysis import (
    calculate_kpis,
    enrich_inventory,
    enrich_orders,
    monthly_kpis,
    supplier_scorecard,
    write_excel_workbook,
    write_powerbi_exports,
    write_raw_csv_exports,
)
from database_connection import (
    generate_demo_data,
    initialize_mysql_schema,
    load_demo_data_to_mysql,
    load_mysql_data,
)
from visualizations import create_charts

ROOT = Path(__file__).resolve().parent
OUTPUT_DIR = ROOT / "outputs"
CHART_DIR = OUTPUT_DIR / "charts"
POWERBI_DIR = OUTPUT_DIR / "powerbi"
RAW_CSV_DIR = OUTPUT_DIR / "raw_csv"

LOGGER = logging.getLogger("supply_chain_analytics")


def prepare_directories() -> None:
    """Create clean output locations without deleting existing user files."""

    CHART_DIR.mkdir(parents=True, exist_ok=True)
    POWERBI_DIR.mkdir(parents=True, exist_ok=True)
    RAW_CSV_DIR.mkdir(parents=True, exist_ok=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Supply chain analytics: MySQL -> Python -> Excel/Power BI")
    parser.add_argument("--mode", choices=["auto", "demo", "mysql"], default="auto", help="Data source. auto tries MySQL, then uses demo data.")
    parser.add_argument("--rows", type=int, default=2500, help="Number of demo orders when using demo mode.")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for reproducible demo data.")
    parser.add_argument(
        "--load-demo-to-mysql",
        action="store_true",
        help="Create the schema and upsert demo data into MySQL before analyzing it. Use with --mode mysql.",
    )
    parser.add_argument(
        "--no-menu",
        action="store_true",
        help="Run the pipeline once and exit without showing the interactive menu.",
    )
    return parser.parse_args()


def get_data(mode: str, rows: int, seed: int):
    if mode in {"auto", "mysql"}:
        try:
            orders, inventory = load_mysql_data()
            if orders.empty:
                raise RuntimeError("MySQL orders table is empty")
            return orders, inventory, "MySQL"
        except Exception as error:  # noqa: BLE001 - auto mode intentionally falls back to demo data.
            if mode == "mysql":
                raise RuntimeError(f"Could not read MySQL: {error}") from error
            LOGGER.warning("MySQL unavailable (%s); using reproducible demo data.", error)
    return (*generate_demo_data(rows, seed), "Demo")


# --------------------------------------------------------------------------
# Interactive menu
# --------------------------------------------------------------------------

def open_path(path: Path) -> None:
    """Open a file or folder with the operating system's default application."""

    path_str = str(path)
    try:
        if sys.platform.startswith("win"):
            os.startfile(path_str)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.run(["open", path_str], check=False)
        else:
            subprocess.run(["xdg-open", path_str], check=False)
        LOGGER.info("Opened: %s", path_str)
    except Exception as error:  # noqa: BLE001 - fall back to telling the user where the files are.
        LOGGER.warning("Could not auto-open %s (%s). Open it manually from that path.", path_str, error)


def menu_open_raw_data() -> None:
    print(f"\nRaw data files are in: {RAW_CSV_DIR}")
    print("  suppliers.csv, warehouses.csv, products.csv, orders.csv, inventory_snapshots.csv")
    open_path(RAW_CSV_DIR)


def menu_open_powerbi_dashboard() -> None:
    pbix_files = list(ROOT.glob("*.pbix")) + list(POWERBI_DIR.glob("*.pbix"))
    if pbix_files:
        print(f"\nOpening Power BI dashboard file: {pbix_files[0]}")
        open_path(pbix_files[0])
        return
    print(f"\nNo .pbix file found yet. Power BI-ready CSVs are in: {POWERBI_DIR}")
    print("  orders.csv, supplier_scorecard.csv, monthly_kpis.csv, inventory_risk.csv")
    print("In Power BI Desktop: Home -> Get Data -> Text/CSV -> import all four files.")
    print("Once you save your report, save it as .pbix in this project's 'powerbi' folder")
    print("so this menu option can open it directly next time.")
    open_path(POWERBI_DIR)


def menu_python_analysis(kpis: pd.DataFrame, scorecard: pd.DataFrame, monthly: pd.DataFrame) -> None:
    print("\n=== KPI Summary (Python analysis) ===")
    print(kpis.to_string(index=False))
    print("\n=== Supplier Scorecard (top 5 by performance score) ===")
    print(scorecard.head(5).to_string(index=False))
    print("\n=== Monthly KPIs (first 5 months) ===")
    print(monthly.head(5).to_string(index=False))
    print(f"\nFull tables are also saved in the Excel workbook: {OUTPUT_DIR / 'supply_chain_analytics.xlsx'}")


def menu_charts() -> None:
    print(f"\nChart images are in: {CHART_DIR}")
    print("  supplier_performance.png, monthly_service_levels.png,")
    print("  inventory_risk_heatmap.png, cost_by_category.png")
    open_path(CHART_DIR)


def run_menu(kpis: pd.DataFrame, scorecard: pd.DataFrame, monthly: pd.DataFrame) -> None:
    if not sys.stdin.isatty():
        # Running non-interactively (e.g. piped/automated). Skip the menu so
        # the script never hangs waiting for input that will never arrive.
        LOGGER.info("Non-interactive session detected; skipping the menu.")
        return

    while True:
        print("\nSupply Chain Analytics — Main Menu")
        print("  1. Open Raw Data")
        print("  2. Open Power BI Dashboard")
        print("  3. Python Analysis")
        print("  4. Charts")
        print("  5. Exit")
        try:
            choice = input("Enter your choice (1-5): ").strip()
        except EOFError:
            break

        if choice == "1":
            menu_open_raw_data()
        elif choice == "2":
            menu_open_powerbi_dashboard()
        elif choice == "3":
            menu_python_analysis(kpis, scorecard, monthly)
        elif choice == "4":
            menu_charts()
        elif choice == "5":
            print("Goodbye.")
            break
        else:
            print("Invalid choice. Please enter a number from 1 to 5.")


def main() -> int:
    args = parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    if args.rows < 1:
        raise ValueError("--rows must be at least 1")
    prepare_directories()

    # 1. Get the data (database_connection.py)
    if args.load_demo_to_mysql:
        if args.mode != "mysql":
            raise ValueError("--load-demo-to-mysql must be used with --mode mysql")
        demo_orders, demo_inventory = generate_demo_data(args.rows, args.seed)
        initialize_mysql_schema()
        load_demo_data_to_mysql(demo_orders, demo_inventory)
        orders, inventory = load_mysql_data()
        source = "MySQL (seeded demo data)"
    else:
        orders, inventory, source = get_data(args.mode, args.rows, args.seed)
    write_raw_csv_exports(orders, inventory, source, RAW_CSV_DIR)

    # 2. Analyze the data (analysis.py)
    orders = enrich_orders(orders)
    inventory = enrich_inventory(inventory)
    kpis = calculate_kpis(orders, inventory)
    scorecard = supplier_scorecard(orders)
    monthly = monthly_kpis(orders)
    write_powerbi_exports(orders, inventory, scorecard, monthly, POWERBI_DIR)
    workbook_path = write_excel_workbook(kpis, orders, inventory, scorecard, monthly, OUTPUT_DIR)

    # 3. Visualize the data (visualizations.py)
    create_charts(orders, inventory, scorecard, monthly, CHART_DIR)

    LOGGER.info("Data source: %s", source)
    LOGGER.info("Orders analyzed: %s", len(orders))
    LOGGER.info("On-time delivery: %.2f%%", kpis.loc[kpis["metric"] == "On-time delivery", "value"].iloc[0])
    LOGGER.info("Outputs: %s", OUTPUT_DIR)
    LOGGER.info("Excel workbook: %s", workbook_path)
    LOGGER.info("Power BI CSV folder: %s", POWERBI_DIR)
    LOGGER.info("Charts: %s", CHART_DIR)

    # 4. Interactive menu
    if not args.no_menu:
        run_menu(kpis, scorecard, monthly)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:  # noqa: BLE001 - provide a concise CLI error.
        LOGGER.error("Pipeline failed: %s", error)
        raise SystemExit(1)
