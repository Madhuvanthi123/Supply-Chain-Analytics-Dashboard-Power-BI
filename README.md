# Supply-Chain-Analytics-Dashboard-Power-BI
End-to-end supply chain analytics solution in Power BI covering inventory, procurement, logistics, and demand performance, with interactive KPIs for data-driven decision making.
# 📦 Supply Chain Analytics using Power BI

## 📌 Project Overview
This project analyzes end-to-end supply chain operations using Power BI to help
businesses improve delivery performance, reduce costs, optimize inventory, and
evaluate supplier reliability. The interactive dashboard turns raw operational
data into actionable insights for supply chain managers.

## 🎯 Business Objectives
- Monitor order fulfillment and on-time delivery performance
- Identify high-cost and delay-prone shipping routes
- Track inventory levels and stock-out risks
- Evaluate supplier performance and lead times
- Analyze sales and demand trends across regions and product categories

## 📊 Key KPIs
| KPI | Description |
|---|---|
| On-Time Delivery % | Orders delivered on or before the promised date |
| Order Fulfillment Rate | Orders fulfilled completely vs. total orders |
| Average Lead Time | Days from order placement to delivery |
| Inventory Turnover | Cost of goods sold ÷ average inventory |
| Stock-Out Rate | Share of items unavailable when demanded |
| Total Shipping Cost | Logistics spend by carrier, route, region |
| Supplier Defect Rate | Quality issues per supplier |

## 🗂️ Dataset
- **Source:** Kaggle / company sample data (mention the exact source and link)
- **Tables:** Orders, Products, Customers, Suppliers, Shipping, Inventory
- **Records:** ~XX,XXX rows (update with your actual count)

## 🛠️ Tools & Technologies
- **Power BI Desktop**: dashboarding and visualization
- **Power Query**: data cleaning and transformation
- **DAX**: calculated measures and columns
- **Data Modeling**: star schema with fact and dimension tables
- **Excel / CSV**: raw data sources

## 🔄 Project Workflow
1. **Data Collection**: imported CSV/Excel files into Power BI
2. **Data Cleaning**: handled nulls, duplicates, and data types in Power Query
3. **Data Modeling**: built a star schema with relationships between tables
4. **DAX Measures**: created KPIs, time intelligence, and ranking measures
5. **Visualization**: designed interactive, multi-page dashboards
6. **Insights**: documented key findings and recommendations

## 📈 Dashboard Pages
1. **Executive Summary**: headline KPIs, trends, regional performance
2. **Inventory Analysis**: stock levels, turnover, reorder alerts
3. **Logistics & Delivery**: carrier performance, delays, shipping cost
4. **Supplier Performance**: lead time, quality, reliability scores
5. **Demand & Sales Analysis**: seasonality, top products, forecasts

## 🧮 Sample DAX Measures
```DAX
On-Time Delivery % =
DIVIDE(
    CALCULATE(COUNTROWS(Orders), Orders[Delivery_Status] = "On Time"),
    COUNTROWS(Orders)
)

Average Lead Time =
AVERAGEX(Orders, DATEDIFF(Orders[Order_Date], Orders[Delivery_Date], DAY))

Inventory Turnover =
DIVIDE(SUM(Sales[COGS]), AVERAGE(Inventory[Stock_Value]))
```

## 💡 Key Insights
- Replace with your real findings, for example:
- Delays are concentrated in two shipping routes, causing XX% of late orders
- A small group of suppliers accounts for most quality defects
- Stock-outs peak during Q4 for fast-moving categories

## ✅ Recommendations
- Renegotiate or replace underperforming carriers/suppliers
- Adjust reorder points for seasonal products
- Consolidate shipments on high-cost routes

## 📸 Dashboard Preview
![Dashboard Screenshot](images/dashboard.png)

## 📁 Repository Structure
