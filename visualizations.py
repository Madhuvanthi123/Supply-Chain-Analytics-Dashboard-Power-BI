"""Visualization layer.

All matplotlib/seaborn chart generation lives here, isolated from data
analysis and database code so charts can be changed without touching
either.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns


def save_chart(chart_dir: Path, filename: str) -> None:
    plt.tight_layout()
    plt.savefig(chart_dir / filename, dpi=160, bbox_inches="tight")
    plt.close()


def create_charts(orders: pd.DataFrame, inventory: pd.DataFrame, scorecard: pd.DataFrame, monthly: pd.DataFrame, chart_dir: Path) -> None:
    """Create matplotlib/seaborn visuals for the dashboard and project review."""

    sns.set_theme(style="whitegrid", context="notebook")

    plt.figure(figsize=(10, 5.5))
    supplier_plot = scorecard.sort_values("performance_score")
    sns.barplot(data=supplier_plot, x="performance_score", y="supplier_name", color="#2a9d8f")
    plt.xlim(0, 100)
    plt.xlabel("Performance score (0-100)")
    plt.ylabel("")
    plt.title("Supplier performance scorecard")
    save_chart(chart_dir, "supplier_performance.png")

    plt.figure(figsize=(11, 5.5))
    monthly_plot = monthly.copy()
    monthly_plot["month_index"] = np.arange(len(monthly_plot))
    sns.lineplot(data=monthly_plot, x="month_index", y="on_time_delivery_pct", marker="o", label="On-time delivery %")
    sns.lineplot(data=monthly_plot, x="month_index", y="fill_rate_pct", marker="o", label="Fill rate %")
    plt.ylim(0, 105)
    plt.xticks(monthly_plot["month_index"], monthly_plot["order_month"], rotation=45)
    plt.xlim(-0.25, max(len(monthly_plot) - 0.75, 0.25))
    plt.xlabel("")
    plt.ylabel("Percentage")
    plt.title("Monthly service-level trend")
    save_chart(chart_dir, "monthly_service_levels.png")

    plt.figure(figsize=(10, 6))
    risk_matrix = inventory.pivot_table(index="category", columns="warehouse_id", values="risk_score", aggfunc="mean")
    sns.heatmap(risk_matrix, annot=True, fmt=".2f", cmap="RdYlGn_r", vmin=1, vmax=3, linewidths=0.5)
    plt.xlabel("Warehouse")
    plt.ylabel("")
    plt.title("Average inventory risk score (1 = healthy, 3 = critical)")
    save_chart(chart_dir, "inventory_risk_heatmap.png")

    plt.figure(figsize=(10, 5.5))
    category_cost = orders.groupby("category", as_index=False)["total_cost"].sum().sort_values("total_cost", ascending=False)
    sns.barplot(data=category_cost, x="total_cost", y="category", color="#457b9d")
    plt.xlabel("Total cost")
    plt.ylabel("")
    plt.title("Supply chain cost by product category")
    save_chart(chart_dir, "cost_by_category.png")
