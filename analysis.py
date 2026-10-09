"""Analysis layer.

Takes raw orders/inventory data (from database_connection.py) and produces
the measures, tables, and export files used by Power BI, Excel, and the
charts in visualizations.py. No MySQL or matplotlib code lives here.
"""

from __future__ import annotations

from pathlib import Path
from statistics import mean, median

import numpy as np
import pandas as pd
from openpyxl import load_workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter

from database_connection import PRODUCTS, SUPPLIERS, WAREHOUSES


def enrich_orders(orders: pd.DataFrame) -> pd.DataFrame:
    """Add reusable measures used by charts, Excel, and Power BI exports."""

    result = orders.copy()
    date_columns = ["order_date", "promised_delivery_date", "actual_delivery_date"]
    for column in date_columns:
        result[column] = pd.to_datetime(result[column])
    result["delivery_delay_days"] = (
        result["actual_delivery_date"] - result["promised_delivery_date"]
    ).dt.days
    result["lead_time_days"] = (result["actual_delivery_date"] - result["order_date"]).dt.days
    result["on_time"] = (result["actual_delivery_date"] <= result["promised_delivery_date"]).astype(int)
    result["fill_rate"] = np.where(
        result["quantity_ordered"] > 0,
        result["quantity_delivered"] / result["quantity_ordered"],
        0,
    )
    result["defect_rate"] = np.where(
        result["quantity_delivered"] > 0,
        result["defect_quantity"] / result["quantity_delivered"],
        0,
    )
    result["purchase_cost"] = result["quantity_ordered"] * result["unit_cost"]
    result["total_cost"] = result["purchase_cost"] + result["shipping_cost"]
    result["order_month"] = result["order_date"].dt.to_period("M").astype(str)
    return result


def enrich_inventory(inventory: pd.DataFrame) -> pd.DataFrame:
    """Add inventory risk measures for the dashboard."""

    result = inventory.copy()
    result["snapshot_date"] = pd.to_datetime(result["snapshot_date"])
    result["days_of_inventory"] = np.where(
        result["demand_qty"] > 0,
        result["on_hand_qty"] / result["demand_qty"] * 30,
        np.nan,
    )
    result["risk_score"] = np.select(
        [result["on_hand_qty"] < result["reorder_point"] * 0.5, result["on_hand_qty"] < result["reorder_point"]],
        [3, 2],
        default=1,
    )
    result["risk_level"] = result["risk_score"].map({1: "Healthy", 2: "High", 3: "Critical"})
    return result


def write_raw_csv_exports(orders: pd.DataFrame, inventory: pd.DataFrame, source: str, raw_csv_dir: Path) -> None:
    """Save the normalized source layer as CSV files for review or MySQL import."""

    if source in {"Demo", "MySQL (seeded demo data)"}:
        SUPPLIERS.to_csv(raw_csv_dir / "suppliers.csv", index=False)
        WAREHOUSES.to_csv(raw_csv_dir / "warehouses.csv", index=False)
        PRODUCTS.to_csv(raw_csv_dir / "products.csv", index=False)

    order_columns = [
        "order_id", "order_date", "supplier_id", "warehouse_id", "product_id",
        "promised_delivery_date", "actual_delivery_date", "quantity_ordered",
        "quantity_delivered", "unit_cost", "shipping_cost", "defect_quantity",
        "stockout_flag", "carrier", "status",
    ]
    raw_orders = orders[order_columns].copy()
    raw_inventory = inventory[
        ["snapshot_date", "warehouse_id", "product_id", "on_hand_qty", "demand_qty", "reorder_point"]
    ].copy()
    for frame in (raw_orders, raw_inventory):
        for date_column in ["order_date", "promised_delivery_date", "actual_delivery_date", "snapshot_date"]:
            if date_column in frame.columns:
                frame[date_column] = pd.to_datetime(frame[date_column]).dt.strftime("%Y-%m-%d")
    raw_orders.to_csv(raw_csv_dir / "orders.csv", index=False)
    raw_inventory.to_csv(raw_csv_dir / "inventory_snapshots.csv", index=False)


def calculate_kpis(orders: pd.DataFrame, inventory: pd.DataFrame) -> pd.DataFrame:
    """Return executive-level KPIs as a tidy two-column table."""

    kpis = {
        "Total orders": len(orders),
        "On-time delivery": mean(orders["on_time"]) * 100 if len(orders) else 0,
        "Average lead time (days)": median(orders["lead_time_days"]) if len(orders) else 0,
        "Fill rate": orders["quantity_delivered"].sum() / max(orders["quantity_ordered"].sum(), 1) * 100,
        "Defect rate": orders["defect_quantity"].sum() / max(orders["quantity_delivered"].sum(), 1) * 100,
        "Stockout rate": orders["stockout_flag"].mean() * 100 if len(orders) else 0,
        "Purchase cost": orders["purchase_cost"].sum(),
        "Shipping cost": orders["shipping_cost"].sum(),
        "Total supply chain cost": orders["total_cost"].sum(),
        "Critical inventory positions": int((inventory["risk_level"] == "Critical").sum()),
    }
    return pd.DataFrame({"metric": list(kpis), "value": list(kpis.values())})


def supplier_scorecard(orders: pd.DataFrame) -> pd.DataFrame:
    """Calculate supplier service, quality, delay, and spend metrics."""

    result = (
        orders.groupby(["supplier_id", "supplier_name", "supplier_country"], as_index=False)
        .agg(
            orders=("order_id", "count"),
            on_time_orders=("on_time", "sum"),
            quantity_ordered=("quantity_ordered", "sum"),
            quantity_delivered=("quantity_delivered", "sum"),
            defect_quantity=("defect_quantity", "sum"),
            average_delay_days=("delivery_delay_days", "mean"),
            average_lead_time_days=("lead_time_days", "mean"),
            total_cost=("total_cost", "sum"),
        )
    )
    result["on_time_delivery_pct"] = result["on_time_orders"] / result["orders"] * 100
    result["fill_rate_pct"] = result["quantity_delivered"] / result["quantity_ordered"] * 100
    result["defect_rate_pct"] = result["defect_quantity"] / result["quantity_delivered"].clip(lower=1) * 100
    result["performance_score"] = (
        result["on_time_delivery_pct"] * 0.40
        + result["fill_rate_pct"] * 0.40
        + (100 - result["defect_rate_pct"].clip(upper=100)) * 0.20
    )
    return result.sort_values("performance_score", ascending=False).round(2)


def monthly_kpis(orders: pd.DataFrame) -> pd.DataFrame:
    """Create the time-series table used by the Power BI trend visual."""

    result = (
        orders.groupby("order_month", as_index=False)
        .agg(
            orders=("order_id", "count"),
            on_time_delivery_pct=("on_time", "mean"),
            quantity_ordered=("quantity_ordered", "sum"),
            quantity_delivered=("quantity_delivered", "sum"),
            total_cost=("total_cost", "sum"),
            average_lead_time_days=("lead_time_days", "mean"),
        )
    )
    result["on_time_delivery_pct"] *= 100
    result["fill_rate_pct"] = result["quantity_delivered"] / result["quantity_ordered"].clip(lower=1) * 100
    return result.round(2)


def write_powerbi_exports(orders: pd.DataFrame, inventory: pd.DataFrame, scorecard: pd.DataFrame, monthly: pd.DataFrame, powerbi_dir: Path) -> None:
    """Write clean, flat files that Power BI can import without transformations."""

    orders_export = orders.copy()
    orders_export["on_time"] = orders_export["on_time"].astype(bool)
    inventory_export = inventory.copy()
    exports = {
        "orders.csv": orders_export,
        "inventory_risk.csv": inventory_export,
        "supplier_scorecard.csv": scorecard,
        "monthly_kpis.csv": monthly,
    }
    for filename, frame in exports.items():
        frame.to_csv(powerbi_dir / filename, index=False)


def write_excel_workbook(kpis: pd.DataFrame, orders: pd.DataFrame, inventory: pd.DataFrame, scorecard: pd.DataFrame, monthly: pd.DataFrame, output_dir: Path) -> Path:
    """Create a formatted workbook for operations reviews."""

    workbook_path = output_dir / "supply_chain_analytics.xlsx"
    sheets = {
        "KPI Summary": kpis,
        "Supplier Scorecard": scorecard,
        "Monthly KPIs": monthly,
        "Inventory Risk": inventory,
        "Orders": orders,
    }
    with pd.ExcelWriter(workbook_path, engine="openpyxl") as writer:
        for sheet_name, frame in sheets.items():
            frame.to_excel(writer, sheet_name=sheet_name, index=False)

    workbook = load_workbook(workbook_path)
    header_fill = PatternFill("solid", fgColor="1F4E78")
    header_font = Font(color="FFFFFF", bold=True)
    for worksheet in workbook.worksheets:
        worksheet.freeze_panes = "A2"
        worksheet.auto_filter.ref = worksheet.dimensions
        for cell in worksheet[1]:
            cell.fill = header_fill
            cell.font = header_font
        for column_cells in worksheet.columns:
            max_length = max(len(str(cell.value or "")) for cell in column_cells[:1000])
            worksheet.column_dimensions[get_column_letter(column_cells[0].column)].width = min(max(max_length + 2, 12), 30)
    workbook.save(workbook_path)
    return workbook_path
