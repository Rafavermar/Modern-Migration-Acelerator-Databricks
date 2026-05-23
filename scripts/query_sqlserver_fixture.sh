#!/usr/bin/env bash
set -euo pipefail

source scripts/lib/load_env.sh
load_dotenv

container="${SQLSERVER_CONTAINER_NAME:-mma-legacy-sqlserver}"

run_sql() {
  local sql="$1"
  printf "%s" "$sql" | docker exec -i "$container" bash -lc 'if [ -x /opt/mssql-tools18/bin/sqlcmd ]; then SQLCMD=/opt/mssql-tools18/bin/sqlcmd; else SQLCMD=/opt/mssql-tools/bin/sqlcmd; fi; "$SQLCMD" -C -S localhost -U sa -P "$MSSQL_SA_PASSWORD" -d LegacySales -W -s "," -i /dev/stdin'
}

if [ "${1:-}" != "" ]; then
  run_sql "$1"
  exit 0
fi

echo "SQL Server objects:"
run_sql "
SET NOCOUNT ON;
SELECT
    SCHEMA_NAME(schema_id) AS schema_name,
    name AS object_name,
    type_desc
FROM sys.objects
WHERE is_ms_shipped = 0
ORDER BY schema_name, type_desc, object_name;
"

echo ""
echo "Row counts:"
run_sql "
SET NOCOUNT ON;
SELECT 'dbo.Customers' AS object_name, COUNT_BIG(*) AS row_count FROM dbo.Customers
UNION ALL
SELECT 'dbo.CustomerOrders' AS object_name, COUNT_BIG(*) AS row_count FROM dbo.CustomerOrders
UNION ALL
SELECT 'mart.DimCustomer' AS object_name, COUNT_BIG(*) AS row_count FROM mart.DimCustomer
UNION ALL
SELECT 'mart.FactOrders' AS object_name, COUNT_BIG(*) AS row_count FROM mart.FactOrders;
"

echo ""
echo "Sample orders:"
run_sql "
SET NOCOUNT ON;
SELECT TOP (10)
    order_id,
    customer_id,
    order_date,
    order_total,
    source_system
FROM dbo.CustomerOrders
ORDER BY order_id;
"

echo ""
echo "Sample fact view:"
run_sql "
SET NOCOUNT ON;
SELECT TOP (10)
    order_id,
    customer_id,
    customer_segment,
    order_date,
    order_total
FROM mart.FactOrders
ORDER BY order_id;
"
