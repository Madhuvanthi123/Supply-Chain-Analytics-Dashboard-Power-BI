CREATE DATABASE IF NOT EXISTS supply_chain_analytics;
USE supply_chain_analytics;

CREATE TABLE IF NOT EXISTS suppliers (
    supplier_id VARCHAR(20) PRIMARY KEY,
    supplier_name VARCHAR(120) NOT NULL,
    supplier_country VARCHAR(80) NOT NULL,
    promised_lead_time_days INT NOT NULL,
    quality_rating DECIMAL(5, 2) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS warehouses (
    warehouse_id VARCHAR(20) PRIMARY KEY,
    warehouse_name VARCHAR(120) NOT NULL,
    region VARCHAR(40) NOT NULL
);

CREATE TABLE IF NOT EXISTS products (
    product_id VARCHAR(20) PRIMARY KEY,
    product_name VARCHAR(120) NOT NULL,
    category VARCHAR(80) NOT NULL,
    unit_cost DECIMAL(12, 2) NOT NULL,
    unit_price DECIMAL(12, 2) NOT NULL,
    reorder_point INT NOT NULL
);

CREATE TABLE IF NOT EXISTS orders (
    order_id VARCHAR(30) PRIMARY KEY,
    order_date DATE NOT NULL,
    supplier_id VARCHAR(20) NOT NULL,
    warehouse_id VARCHAR(20) NOT NULL,
    product_id VARCHAR(20) NOT NULL,
    promised_delivery_date DATE NOT NULL,
    actual_delivery_date DATE NOT NULL,
    quantity_ordered INT NOT NULL,
    quantity_delivered INT NOT NULL,
    unit_cost DECIMAL(12, 2) NOT NULL,
    shipping_cost DECIMAL(12, 2) NOT NULL,
    defect_quantity INT NOT NULL DEFAULT 0,
    stockout_flag BOOLEAN NOT NULL DEFAULT FALSE,
    carrier VARCHAR(60),
    status VARCHAR(30) NOT NULL,
    CONSTRAINT fk_orders_supplier FOREIGN KEY (supplier_id) REFERENCES suppliers(supplier_id),
    CONSTRAINT fk_orders_warehouse FOREIGN KEY (warehouse_id) REFERENCES warehouses(warehouse_id),
    CONSTRAINT fk_orders_product FOREIGN KEY (product_id) REFERENCES products(product_id),
    INDEX idx_orders_order_date (order_date),
    INDEX idx_orders_supplier (supplier_id),
    INDEX idx_orders_warehouse (warehouse_id)
);

CREATE TABLE IF NOT EXISTS inventory_snapshots (
    snapshot_date DATE NOT NULL,
    warehouse_id VARCHAR(20) NOT NULL,
    product_id VARCHAR(20) NOT NULL,
    on_hand_qty INT NOT NULL,
    demand_qty INT NOT NULL,
    reorder_point INT NOT NULL,
    PRIMARY KEY (snapshot_date, warehouse_id, product_id),
    CONSTRAINT fk_inventory_warehouse FOREIGN KEY (warehouse_id) REFERENCES warehouses(warehouse_id),
    CONSTRAINT fk_inventory_product FOREIGN KEY (product_id) REFERENCES products(product_id),
    INDEX idx_inventory_risk (on_hand_qty, reorder_point)
);

-- Optional SQL view for analysts who want to inspect the same measures that
-- the Python pipeline exports to Power BI.
CREATE OR REPLACE VIEW vw_order_analytics AS
SELECT
    o.order_id,
    o.order_date,
    o.supplier_id,
    s.supplier_name,
    s.supplier_country,
    o.warehouse_id,
    w.warehouse_name,
    w.region,
    o.product_id,
    p.product_name,
    p.category,
    o.promised_delivery_date,
    o.actual_delivery_date,
    DATEDIFF(o.actual_delivery_date, o.promised_delivery_date) AS delivery_delay_days,
    DATEDIFF(o.actual_delivery_date, o.order_date) AS lead_time_days,
    CASE WHEN o.actual_delivery_date <= o.promised_delivery_date THEN 1 ELSE 0 END AS on_time,
    o.quantity_ordered,
    o.quantity_delivered,
    ROUND(o.quantity_delivered / NULLIF(o.quantity_ordered, 0), 4) AS fill_rate,
    o.defect_quantity,
    ROUND(o.defect_quantity / NULLIF(o.quantity_delivered, 0), 4) AS defect_rate,
    ROUND(o.quantity_ordered * o.unit_cost, 2) AS purchase_cost,
    ROUND(o.quantity_ordered * o.unit_cost + o.shipping_cost, 2) AS total_cost,
    o.stockout_flag,
    o.carrier,
    o.status
FROM orders AS o
JOIN suppliers AS s ON s.supplier_id = o.supplier_id
JOIN warehouses AS w ON w.warehouse_id = o.warehouse_id
JOIN products AS p ON p.product_id = o.product_id;







USE supply_chain_analytics;

-- 1. Executive KPI summary
SELECT
    COUNT(*) AS total_orders,
    ROUND(AVG(on_time) * 100, 2) AS on_time_delivery_pct,
    ROUND(SUM(quantity_delivered) / NULLIF(SUM(quantity_ordered), 0) * 100, 2) AS fill_rate_pct,
    ROUND(SUM(defect_quantity) / NULLIF(SUM(quantity_delivered), 0) * 100, 2) AS defect_rate_pct,
    ROUND(AVG(stockout_flag) * 100, 2) AS stockout_rate_pct,
    ROUND(SUM(total_cost), 2) AS total_supply_chain_cost
FROM vw_order_analytics;

-- 2. Supplier scorecard
SELECT
    supplier_id,
    supplier_name,
    supplier_country,
    COUNT(*) AS orders,
    ROUND(AVG(on_time) * 100, 2) AS on_time_delivery_pct,
    ROUND(SUM(quantity_delivered) / NULLIF(SUM(quantity_ordered), 0) * 100, 2) AS fill_rate_pct,
    ROUND(SUM(defect_quantity) / NULLIF(SUM(quantity_delivered), 0) * 100, 2) AS defect_rate_pct,
    ROUND(AVG(delivery_delay_days), 2) AS average_delay_days,
    ROUND(SUM(total_cost), 2) AS total_cost
FROM vw_order_analytics
GROUP BY supplier_id, supplier_name, supplier_country
ORDER BY on_time_delivery_pct DESC, defect_rate_pct ASC;

-- 3. Monthly trend for Power BI or an operations review
SELECT
    DATE_FORMAT(order_date, '%Y-%m') AS order_month,
    COUNT(*) AS orders,
    ROUND(AVG(on_time) * 100, 2) AS on_time_delivery_pct,
    ROUND(SUM(quantity_delivered) / NULLIF(SUM(quantity_ordered), 0) * 100, 2) AS fill_rate_pct,
    ROUND(AVG(lead_time_days), 2) AS average_lead_time_days,
    ROUND(SUM(total_cost), 2) AS total_cost
FROM vw_order_analytics
GROUP BY DATE_FORMAT(order_date, '%Y-%m')
ORDER BY order_month;

-- 4. Inventory risk positions
SELECT
    i.snapshot_date,
    i.warehouse_id,
    w.warehouse_name,
    w.region,
    i.product_id,
    p.product_name,
    p.category,
    i.on_hand_qty,
    i.demand_qty,
    i.reorder_point,
    ROUND(i.on_hand_qty / NULLIF(i.demand_qty, 0) * 30, 2) AS days_of_inventory,
    CASE
        WHEN i.on_hand_qty < i.reorder_point * 0.5 THEN 'Critical'
        WHEN i.on_hand_qty < i.reorder_point THEN 'High'
        ELSE 'Healthy'
    END AS risk_level
FROM inventory_snapshots AS i
JOIN warehouses AS w ON w.warehouse_id = i.warehouse_id
JOIN products AS p ON p.product_id = i.product_id
ORDER BY FIELD(risk_level, 'Critical', 'High', 'Healthy'), i.snapshot_date DESC;