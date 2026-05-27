param(
    [string]$Query = ""
)

$ErrorActionPreference = "Stop"

function Import-DotEnv {
    param([string]$Path = ".env")

    if (-not (Test-Path $Path)) {
        return
    }

    Get-Content $Path | ForEach-Object {
        $line = $_.Trim()
        if (-not $line -or $line.StartsWith("#") -or -not $line.Contains("=")) {
            return
        }

        $parts = $line.Split("=", 2)
        $name = $parts[0].Trim()
        $value = $parts[1].Trim().Trim('"').Trim("'")
        [Environment]::SetEnvironmentVariable($name, $value, "Process")
    }
}

function Invoke-LegacySql {
    param([string]$Sql)

    $Sql | docker exec -i $script:Container bash -lc 'if [ -x /opt/mssql-tools18/bin/sqlcmd ]; then SQLCMD=/opt/mssql-tools18/bin/sqlcmd; else SQLCMD=/opt/mssql-tools/bin/sqlcmd; fi; "$SQLCMD" -C -S localhost -U sa -P "$MSSQL_SA_PASSWORD" -d LegacySales -W -s "," -i /dev/stdin'
}

Import-DotEnv

$script:Container = if ($env:SQLSERVER_CONTAINER_NAME) { $env:SQLSERVER_CONTAINER_NAME } else { "mma-legacy-sqlserver" }

if ($Query) {
    Invoke-LegacySql $Query
    exit 0
}

Write-Host "SQL Server objects:"
Invoke-LegacySql @"
SET NOCOUNT ON;
SELECT
    SCHEMA_NAME(schema_id) AS schema_name,
    name AS object_name,
    type_desc
FROM sys.objects
WHERE is_ms_shipped = 0
ORDER BY schema_name, type_desc, object_name;
"@

Write-Host ""
Write-Host "Row counts:"
Invoke-LegacySql @"
SET NOCOUNT ON;
SELECT 'dbo.Customers' AS object_name, COUNT_BIG(*) AS row_count FROM dbo.Customers
UNION ALL
SELECT 'dbo.CustomerOrders' AS object_name, COUNT_BIG(*) AS row_count FROM dbo.CustomerOrders
UNION ALL
SELECT 'mart.DimCustomer' AS object_name, COUNT_BIG(*) AS row_count FROM mart.DimCustomer
UNION ALL
SELECT 'mart.FactOrders' AS object_name, COUNT_BIG(*) AS row_count FROM mart.FactOrders;
"@

Write-Host ""
Write-Host "Sample orders:"
Invoke-LegacySql @"
SET NOCOUNT ON;
SELECT TOP (10)
    order_id,
    customer_id,
    order_date,
    order_total,
    source_system
FROM dbo.CustomerOrders
ORDER BY order_id;
"@

Write-Host ""
Write-Host "Sample fact view:"
Invoke-LegacySql @"
SET NOCOUNT ON;
SELECT TOP (10)
    order_id,
    customer_id,
    customer_segment,
    order_date,
    order_total
FROM mart.FactOrders
ORDER BY order_id;
"@
