#!/usr/bin/env bash
set -euo pipefail

if [ -f .env ]; then
  set -a
  . ./.env
  set +a
fi

container="${SQLSERVER_CONTAINER_NAME:-mma-legacy-sqlserver}"
output_dir="${LOCAL_METADATA_OUTPUT_DIR:-local_outputs/legacy_metadata}"
output_file="$output_dir/sqlserver_inventory.csv"

mkdir -p "$output_dir"

cat > "$output_file" <<'CSV'
source_system,database,schema,table,object_name,object_type,row_count,owner,criticality,engine,location,format,depends_on
CSV

docker exec "$container" bash -lc 'if [ -x /opt/mssql-tools18/bin/sqlcmd ]; then SQLCMD=/opt/mssql-tools18/bin/sqlcmd; else SQLCMD=/opt/mssql-tools/bin/sqlcmd; fi; "$SQLCMD" -C -S localhost -U sa -P "$MSSQL_SA_PASSWORD" -d LegacySales -W -s "," -h -1 -Q "
SET NOCOUNT ON;
WITH row_counts AS (
    SELECT
        object_id,
        SUM(row_count) AS row_count
    FROM sys.dm_db_partition_stats
    WHERE index_id IN (0, 1)
    GROUP BY object_id
)
SELECT
    '\''sql_server_docker'\'' AS source_system,
    DB_NAME() AS [database],
    SCHEMA_NAME(o.schema_id) AS [schema],
    CASE WHEN o.type = '\''U'\'' THEN o.name ELSE '\'''\'' END AS [table],
    o.name AS object_name,
    CASE
        WHEN o.type = '\''U'\'' THEN '\''table'\''
        WHEN o.type = '\''V'\'' THEN '\''view'\''
        WHEN o.type = '\''P'\'' THEN '\''stored_procedure'\''
        ELSE LOWER(o.type_desc)
    END AS object_type,
    COALESCE(CONVERT(VARCHAR(30), rc.row_count), '\'''\'' ) AS row_count,
    '\''local-fixture'\'' AS owner,
    CASE WHEN o.name IN ('\''CustomerOrders'\'', '\''FactOrders'\'', '\''usp_build_fact_orders'\'') THEN '\''high'\'' ELSE '\''medium'\'' END AS criticality,
    '\''SQL Server 2022 Docker'\'' AS engine,
    '\'''\'' AS location,
    '\'''\'' AS format,
    CASE
        WHEN o.name = '\''FactOrders'\'' THEN '\''LegacySales.dbo.CustomerOrders|LegacySales.mart.DimCustomer'\''
        WHEN o.name = '\''DimCustomer'\'' THEN '\''LegacySales.dbo.Customers'\''
        WHEN o.name = '\''usp_build_fact_orders'\'' THEN '\''LegacySales.dbo.CustomerOrders|LegacySales.mart.DimCustomer'\''
        ELSE '\'''\''
    END AS depends_on
FROM sys.objects AS o
LEFT JOIN row_counts AS rc
    ON o.object_id = rc.object_id
WHERE o.type IN ('\''U'\'', '\''V'\'', '\''P'\'')
  AND o.is_ms_shipped = 0
ORDER BY object_type, [schema], object_name;
"' >> "$output_file"

echo "Wrote $output_file"
