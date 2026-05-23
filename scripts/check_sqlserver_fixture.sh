#!/usr/bin/env bash
set -euo pipefail

source scripts/lib/load_env.sh
load_dotenv

container="${SQLSERVER_CONTAINER_NAME:-mma-legacy-sqlserver}"

query="
SET NOCOUNT ON;
SELECT 'dbo.Customers' AS object_name, COUNT_BIG(*) AS row_count FROM dbo.Customers
UNION ALL
SELECT 'dbo.CustomerOrders' AS object_name, COUNT_BIG(*) AS row_count FROM dbo.CustomerOrders
UNION ALL
SELECT 'mart.DimCustomer' AS object_name, COUNT_BIG(*) AS row_count FROM mart.DimCustomer
UNION ALL
SELECT 'mart.FactOrders' AS object_name, COUNT_BIG(*) AS row_count FROM mart.FactOrders;
"

echo "SQL Server fixture data counts:"
printf "%s" "$query" | docker exec -i "$container" bash -lc 'if [ -x /opt/mssql-tools18/bin/sqlcmd ]; then SQLCMD=/opt/mssql-tools18/bin/sqlcmd; else SQLCMD=/opt/mssql-tools/bin/sqlcmd; fi; "$SQLCMD" -C -S localhost -U sa -P "$MSSQL_SA_PASSWORD" -d LegacySales -W -s "," -h -1 -i /dev/stdin' |
  sed '/rows affected/d;/^[[:space:]]*$/d'
