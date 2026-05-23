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

Import-DotEnv

$container = if ($env:SQLSERVER_CONTAINER_NAME) { $env:SQLSERVER_CONTAINER_NAME } else { "mma-legacy-sqlserver" }

$query = @"
SET NOCOUNT ON;
SELECT 'dbo.Customers' AS object_name, COUNT_BIG(*) AS row_count FROM dbo.Customers
UNION ALL
SELECT 'dbo.CustomerOrders' AS object_name, COUNT_BIG(*) AS row_count FROM dbo.CustomerOrders
UNION ALL
SELECT 'mart.DimCustomer' AS object_name, COUNT_BIG(*) AS row_count FROM mart.DimCustomer
UNION ALL
SELECT 'mart.FactOrders' AS object_name, COUNT_BIG(*) AS row_count FROM mart.FactOrders;
"@

$rows = $query | docker exec -i $container bash -lc 'if [ -x /opt/mssql-tools18/bin/sqlcmd ]; then SQLCMD=/opt/mssql-tools18/bin/sqlcmd; else SQLCMD=/opt/mssql-tools/bin/sqlcmd; fi; "$SQLCMD" -C -S localhost -U sa -P "$MSSQL_SA_PASSWORD" -d LegacySales -W -s "," -h -1 -i /dev/stdin'

if ($LASTEXITCODE -ne 0) {
    throw "SQL Server fixture check failed."
}

Write-Host "SQL Server fixture data counts:"
$rows |
    Where-Object { $_ -and $_.Trim() -and $_ -notmatch "rows affected" } |
    ForEach-Object { Write-Host $_ }
