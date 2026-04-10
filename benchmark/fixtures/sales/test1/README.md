# Sales Pipeline Fixtures

Standard sales data for testing join, group-by, sort, and filter operations.

## Files

| File | Rows | Description |
|------|------|-------------|
| `orders.csv` | 50 | Sales orders with product/customer references |
| `customers.csv` | 20 | Customer profiles with segments |
| `products.csv` | 10 | Product catalog with categories and prices |

## Schemas

### orders.csv

| Column | Type | Description |
|--------|------|-------------|
| order_id | string | Unique order identifier (ORD0001-ORD0050) |
| product_id | string | FK to products.product_id |
| customer_id | string | FK to customers.customer_id |
| region | string | North, South, East, West (denormalized from customer) |
| amount | float | Total order amount in USD ($10-$2500) |
| quantity | int | Units ordered (1-5) |
| order_date | date | YYYY-MM-DD, range 2025-01 to 2025-12 |

### customers.csv

| Column | Type | Description |
|--------|------|-------------|
| customer_id | string | Unique customer identifier (CUST001-CUST020) |
| name | string | Full name |
| email | string | Email address (example.com domain) |
| region | string | North, South, East, West |
| segment | string | Enterprise, SMB, Individual |
| signup_date | date | YYYY-MM-DD, range 2023-01 to 2024-12 |

### products.csv

| Column | Type | Description |
|--------|------|-------------|
| product_id | string | Unique product identifier (PROD001-PROD010) |
| name | string | Product name |
| category | string | Electronics, Software, Services, Hardware |
| unit_price | float | Price per unit in USD |

## Join Keys

- `orders.product_id` -> `products.product_id`
- `orders.customer_id` -> `customers.customer_id`

## Intended Use

Benchmark scenarios that reference this fixture test:

1. **Join operations**: Three-way join of orders + customers + products
2. **Group-by aggregation**: Revenue by region, segment, category
3. **Sort**: Top orders by amount, chronological ordering
4. **Filter**: Date range filtering, segment filtering
5. **Window functions**: Running totals, rank within region

## Data Characteristics

- All foreign keys are valid (every order references an existing product and customer)
- Region is denormalized in orders (matches the customer's region)
- Amount varies based on product price * quantity with slight noise
- Date distribution is uniform across 2025
