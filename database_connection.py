"""Database connection layer.

Handles everything related to data *sourcing*:
- Reference/dimension tables (suppliers, warehouses, products)
- Reproducible demo data generation (used when MySQL isn't available)
- MySQL 8.0 (MySQL Workbench CE) connection, schema creation, and reads/writes

No analysis or chart logic lives here — see analysis.py and visualizations.py.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

import numpy as np
import pandas as pd

try:
    from dotenv import load_dotenv
except ImportError:  # python-dotenv not installed; .env files simply won't be auto-loaded.
    load_dotenv = None

try:
    import mysql.connector
except ImportError:  # Demo mode does not require a local MySQL installation.
    mysql = None


ROOT = Path(__file__).resolve().parent

if load_dotenv is not None:
    # Automatically read MYSQL_* values from a ".env" file in the project
    # folder (if present) into the real environment, so you don't have to
    # retype $env:MYSQL_... commands every VS Code session. Copy
    # ".env.example" to ".env" and fill in your real values to use this.
    load_dotenv(ROOT / ".env")
LOGGER = logging.getLogger("supply_chain_analytics.database_connection")

SUPPLIERS = pd.DataFrame(
    [
        ("SUP-001", "Apex Components", "India", 4, 96.0),
        ("SUP-002", "BlueRiver Parts", "Vietnam", 7, 91.0),
        ("SUP-003", "Crestline Manufacturing", "China", 9, 87.0),
        ("SUP-004", "Delta Industrial", "Malaysia", 6, 93.0),
        ("SUP-005", "Evergreen Materials", "India", 5, 89.0),
        ("SUP-006", "Frontier Supply", "Thailand", 8, 84.0),
    ],
    columns=["supplier_id", "supplier_name", "supplier_country", "promised_lead_time_days", "quality_rating"],
)

WAREHOUSES = pd.DataFrame(
    [
        ("WH-001", "Mumbai DC", "West"),
        ("WH-002", "Delhi DC", "North"),
        ("WH-003", "Bengaluru DC", "South"),
        ("WH-004", "Kolkata DC", "East"),
    ],
    columns=["warehouse_id", "warehouse_name", "region"],
)

PRODUCTS = pd.DataFrame(
    [
        ("PRD-001", "Laptop Stand", "Accessories", 22.0, 39.0, 80),
        ("PRD-002", "USB-C Dock", "Accessories", 48.0, 89.0, 70),
        ("PRD-003", "Wireless Keyboard", "Peripherals", 31.0, 59.0, 90),
        ("PRD-004", "Wireless Mouse", "Peripherals", 14.0, 29.0, 120),
        ("PRD-005", "27-inch Monitor", "Displays", 155.0, 249.0, 45),
        ("PRD-006", "Webcam", "Peripherals", 38.0, 79.0, 65),
        ("PRD-007", "Noise-cancel Headset", "Audio", 52.0, 99.0, 55),
        ("PRD-008", "Mechanical Keyboard", "Peripherals", 67.0, 129.0, 50),
        ("PRD-009", "Portable SSD", "Storage", 78.0, 139.0, 45),
        ("PRD-010", "Wi-Fi Router", "Networking", 44.0, 85.0, 75),
        ("PRD-011", "HDMI Cable", "Accessories", 7.0, 15.0, 200),
        ("PRD-012", "Power Strip", "Accessories", 16.0, 31.0, 140),
    ],
    columns=["product_id", "product_name", "category", "unit_cost", "unit_price", "reorder_point"],
)


def generate_demo_data(rows: int, seed: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Create realistic order and inventory data for local development/demo runs."""

    rng = np.random.default_rng(seed)
    order_dates = pd.Series(
        rng.choice(pd.date_range("2024-01-01", "2024-12-31", freq="D"), size=rows),
        name="order_date",
    )
    supplier_ids = rng.choice(SUPPLIERS["supplier_id"], size=rows)
    warehouse_ids = rng.choice(WAREHOUSES["warehouse_id"], size=rows)
    product_ids = rng.choice(PRODUCTS["product_id"], size=rows)

    supplier_lookup = SUPPLIERS.set_index("supplier_id")
    product_lookup = PRODUCTS.set_index("product_id")
    supplier_lead = pd.Series(supplier_ids).map(supplier_lookup["promised_lead_time_days"]).to_numpy()
    supplier_quality = pd.Series(supplier_ids).map(supplier_lookup["quality_rating"]).to_numpy()
    base_cost = pd.Series(product_ids).map(product_lookup["unit_cost"]).to_numpy()
    product_price = pd.Series(product_ids).map(product_lookup["unit_price"]).to_numpy()
    reorder_point = pd.Series(product_ids).map(product_lookup["reorder_point"]).to_numpy()

    promised_dates = order_dates + pd.to_timedelta(supplier_lead, unit="D")
    supplier_delay_bias = (100 - supplier_quality) / 18
    delivery_delay = np.maximum(
        -1,
        np.rint(rng.normal(loc=supplier_delay_bias, scale=2.8, size=rows)),
    ).astype(int)
    actual_dates = promised_dates + pd.to_timedelta(delivery_delay, unit="D")

    quantity_ordered = rng.integers(5, 180, size=rows)
    fill_mean = np.clip(0.97 - ((100 - supplier_quality) / 220), 0.82, 0.98)
    fill_ratio = np.clip(rng.normal(fill_mean, 0.07, size=rows), 0.55, 1.0)
    quantity_delivered = np.floor(quantity_ordered * fill_ratio).astype(int)
    defect_rate = np.clip(rng.normal((100 - supplier_quality) / 1650, 0.008, size=rows), 0.0, 0.08)
    defect_quantity = np.minimum(quantity_delivered, np.floor(quantity_delivered * defect_rate).astype(int))
    unit_cost = np.round(base_cost * rng.normal(1.0, 0.035, size=rows), 2)
    shipping_cost = np.round(7.5 + quantity_ordered * rng.uniform(0.25, 1.15, size=rows), 2)
    stockout_probability = np.clip(0.05 + (1 - fill_ratio) * 0.75 + (quantity_ordered > reorder_point) * 0.08, 0.02, 0.45)
    stockout_flag = rng.random(rows) < stockout_probability
    carriers = rng.choice(["DHL", "FedEx", "BlueDart", "Delhivery"], size=rows, p=[0.25, 0.20, 0.30, 0.25])

    orders = pd.DataFrame(
        {
            "order_id": [f"ORD-{index:06d}" for index in range(1, rows + 1)],
            "order_date": order_dates,
            "supplier_id": supplier_ids,
            "warehouse_id": warehouse_ids,
            "product_id": product_ids,
            "promised_delivery_date": promised_dates,
            "actual_delivery_date": actual_dates,
            "quantity_ordered": quantity_ordered,
            "quantity_delivered": quantity_delivered,
            "unit_cost": unit_cost,
            "unit_price": product_price,
            "shipping_cost": shipping_cost,
            "defect_quantity": defect_quantity,
            "stockout_flag": stockout_flag.astype(int),
            "carrier": carriers,
            "status": np.where(quantity_delivered < quantity_ordered * 0.8, "Backorder", "Delivered"),
        }
    )
    orders = orders.merge(SUPPLIERS, on="supplier_id", how="left").merge(PRODUCTS[["product_id", "product_name", "category"]], on="product_id", how="left")
    orders = orders.merge(WAREHOUSES, on="warehouse_id", how="left")

    snapshot_dates = pd.date_range("2024-01-31", "2024-12-31", freq="ME")
    inventory_rows: list[dict[str, object]] = []
    for snapshot_date in snapshot_dates:
        for warehouse_id in WAREHOUSES["warehouse_id"]:
            for product_id in PRODUCTS["product_id"]:
                product = product_lookup.loc[product_id]
                monthly_demand = int(rng.integers(20, 160))
                on_hand = int(max(0, rng.normal(product["reorder_point"] * 1.25, product["reorder_point"] * 0.65)))
                inventory_rows.append(
                    {
                        "snapshot_date": snapshot_date,
                        "warehouse_id": warehouse_id,
                        "product_id": product_id,
                        "on_hand_qty": on_hand,
                        "demand_qty": monthly_demand,
                        "reorder_point": int(product["reorder_point"]),
                        "category": product["category"],
                        "product_name": product["product_name"],
                    }
                )
    inventory = pd.DataFrame(inventory_rows).merge(WAREHOUSES, on="warehouse_id", how="left")
    return orders, inventory


def mysql_config() -> dict[str, object]:
    """Read MySQL Workbench-compatible connection settings from environment variables."""

    return {
        "host": os.getenv("MYSQL_HOST", "127.0.0.1"),
        "port": int(os.getenv("MYSQL_PORT", "3307")),
        "user": os.getenv("MYSQL_USER", "root"),
        "password": os.getenv("MYSQL_PASSWORD", "Madhu@pumo123"),
        "database": os.getenv("MYSQL_DATABASE", "supply_chain_analytics"),
    }


def initialize_mysql_schema() -> None:
    """Create the database objects from sql/schema.sql in MySQL Workbench."""

    if mysql is None:
        raise RuntimeError("mysql-connector-python is not installed. Run: pip install -r requirements.txt")

    server_settings = mysql_config()
    server_settings.pop("database", None)
    connection = mysql.connector.connect(**server_settings)
    try:
        schema_text = (ROOT / "sql" / "schema.sql").read_text(encoding="utf-8")
        # The project schema contains ordinary semicolon-terminated statements
        # and no stored procedures, so removing comment lines is sufficient.
        schema_without_comments = "\n".join(
            line for line in schema_text.splitlines() if not line.strip().startswith("--")
        )
        cursor = connection.cursor()
        for statement in schema_without_comments.split(";"):
            statement = statement.strip()
            if statement:
                cursor.execute(statement)
        connection.commit()
    finally:
        connection.close()


def load_demo_data_to_mysql(orders: pd.DataFrame, inventory: pd.DataFrame) -> None:
    """Upsert generated dimensions and facts into MySQL for an end-to-end run."""

    if mysql is None:
        raise RuntimeError("mysql-connector-python is not installed. Run: pip install -r requirements.txt")

    connection = mysql.connector.connect(**mysql_config())
    try:
        cursor = connection.cursor()
        cursor.executemany(
            """
            INSERT INTO suppliers
                (supplier_id, supplier_name, supplier_country, promised_lead_time_days, quality_rating)
            VALUES (%s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                supplier_name = VALUES(supplier_name), supplier_country = VALUES(supplier_country),
                promised_lead_time_days = VALUES(promised_lead_time_days), quality_rating = VALUES(quality_rating)
            """,
            [tuple(row) for row in SUPPLIERS.itertuples(index=False, name=None)],
        )
        cursor.executemany(
            """
            INSERT INTO warehouses (warehouse_id, warehouse_name, region)
            VALUES (%s, %s, %s)
            ON DUPLICATE KEY UPDATE warehouse_name = VALUES(warehouse_name), region = VALUES(region)
            """,
            [tuple(row) for row in WAREHOUSES.itertuples(index=False, name=None)],
        )
        cursor.executemany(
            """
            INSERT INTO products
                (product_id, product_name, category, unit_cost, unit_price, reorder_point)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                product_name = VALUES(product_name), category = VALUES(category),
                unit_cost = VALUES(unit_cost), unit_price = VALUES(unit_price), reorder_point = VALUES(reorder_point)
            """,
            [tuple(row) for row in PRODUCTS.itertuples(index=False, name=None)],
        )

        order_payload = []
        order_columns = [
            "order_id", "order_date", "supplier_id", "warehouse_id", "product_id",
            "promised_delivery_date", "actual_delivery_date", "quantity_ordered",
            "quantity_delivered", "unit_cost", "shipping_cost", "defect_quantity",
            "stockout_flag", "carrier", "status",
        ]
        for row in orders[order_columns].itertuples(index=False, name=None):
            order_payload.append(
                (
                    str(row[0]), pd.Timestamp(row[1]).date(), str(row[2]), str(row[3]), str(row[4]),
                    pd.Timestamp(row[5]).date(), pd.Timestamp(row[6]).date(), int(row[7]), int(row[8]),
                    float(row[9]), float(row[10]), int(row[11]), bool(row[12]), str(row[13]), str(row[14]),
                )
            )
        cursor.executemany(
            """
            INSERT INTO orders
                (order_id, order_date, supplier_id, warehouse_id, product_id,
                 promised_delivery_date, actual_delivery_date, quantity_ordered,
                 quantity_delivered, unit_cost, shipping_cost, defect_quantity,
                 stockout_flag, carrier, status)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                order_date = VALUES(order_date), supplier_id = VALUES(supplier_id),
                warehouse_id = VALUES(warehouse_id), product_id = VALUES(product_id),
                promised_delivery_date = VALUES(promised_delivery_date),
                actual_delivery_date = VALUES(actual_delivery_date),
                quantity_ordered = VALUES(quantity_ordered), quantity_delivered = VALUES(quantity_delivered),
                unit_cost = VALUES(unit_cost), shipping_cost = VALUES(shipping_cost),
                defect_quantity = VALUES(defect_quantity), stockout_flag = VALUES(stockout_flag),
                carrier = VALUES(carrier), status = VALUES(status)
            """,
            order_payload,
        )

        inventory_payload = []
        inventory_columns = ["snapshot_date", "warehouse_id", "product_id", "on_hand_qty", "demand_qty", "reorder_point"]
        for row in inventory[inventory_columns].itertuples(index=False, name=None):
            inventory_payload.append(
                (pd.Timestamp(row[0]).date(), str(row[1]), str(row[2]), int(row[3]), int(row[4]), int(row[5]))
            )
        cursor.executemany(
            """
            INSERT INTO inventory_snapshots
                (snapshot_date, warehouse_id, product_id, on_hand_qty, demand_qty, reorder_point)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                on_hand_qty = VALUES(on_hand_qty), demand_qty = VALUES(demand_qty), reorder_point = VALUES(reorder_point)
            """,
            inventory_payload,
        )
        connection.commit()
        LOGGER.info("Loaded %s demo orders and %s inventory snapshots into MySQL.", len(order_payload), len(inventory_payload))
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def load_mysql_data() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Read the fact tables created by sql/schema.sql from MySQL."""

    if mysql is None:
        raise RuntimeError("mysql-connector-python is not installed. Run: pip install -r requirements.txt")

    connection = mysql.connector.connect(**mysql_config())
    try:
        order_query = """
            SELECT
                o.order_id, o.order_date, o.supplier_id, o.warehouse_id, o.product_id,
                o.promised_delivery_date, o.actual_delivery_date,
                o.quantity_ordered, o.quantity_delivered, o.unit_cost,
                p.unit_price, o.shipping_cost, o.defect_quantity,
                o.stockout_flag, o.carrier, o.status,
                s.supplier_name, s.supplier_country,
                s.promised_lead_time_days, s.quality_rating,
                p.product_name, p.category,
                w.warehouse_name, w.region
            FROM orders AS o
            INNER JOIN suppliers AS s ON s.supplier_id = o.supplier_id
            INNER JOIN products AS p ON p.product_id = o.product_id
            INNER JOIN warehouses AS w ON w.warehouse_id = o.warehouse_id
        """
        inventory_query = """
            SELECT
                i.snapshot_date, i.warehouse_id, i.product_id,
                i.on_hand_qty, i.demand_qty, i.reorder_point,
                p.product_name, p.category, w.warehouse_name, w.region
            FROM inventory_snapshots AS i
            INNER JOIN products AS p ON p.product_id = i.product_id
            INNER JOIN warehouses AS w ON w.warehouse_id = i.warehouse_id
        """
        cursor = connection.cursor(dictionary=True)
        cursor.execute(order_query)
        orders = pd.DataFrame(cursor.fetchall())
        cursor.execute(inventory_query)
        inventory = pd.DataFrame(cursor.fetchall())
        return orders, inventory
    finally:
        connection.close()
