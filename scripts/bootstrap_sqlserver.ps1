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
$initSql = "samples/sqlserver/init/00_create_legacy_sales.sql"

docker compose -f docker-compose.yml up -d legacy-sqlserver

$ready = $false
for ($attempt = 1; $attempt -le 60; $attempt++) {
    docker exec $container bash -lc 'if [ -x /opt/mssql-tools18/bin/sqlcmd ]; then SQLCMD=/opt/mssql-tools18/bin/sqlcmd; else SQLCMD=/opt/mssql-tools/bin/sqlcmd; fi; "$SQLCMD" -C -S localhost -U sa -P "$MSSQL_SA_PASSWORD" -Q "SELECT 1"' *> $null
    if ($LASTEXITCODE -eq 0) {
        $ready = $true
        break
    }

    Start-Sleep -Seconds 2
}

if (-not $ready) {
    throw "SQL Server did not become ready in time."
}

Get-Content $initSql -Raw | docker exec -i $container bash -lc 'if [ -x /opt/mssql-tools18/bin/sqlcmd ]; then SQLCMD=/opt/mssql-tools18/bin/sqlcmd; else SQLCMD=/opt/mssql-tools/bin/sqlcmd; fi; "$SQLCMD" -C -S localhost -U sa -P "$MSSQL_SA_PASSWORD" -d master -i /dev/stdin'

$port = if ($env:MSSQL_PORT) { $env:MSSQL_PORT } else { "1433" }
Write-Host "Local SQL Server fixture is ready: localhost:$port, database LegacySales."
