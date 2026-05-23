#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
. "$script_dir/lib/load_env.sh"
load_dotenv ".env"

container="${SQLSERVER_CONTAINER_NAME:-mma-legacy-sqlserver}"
init_sql="samples/sqlserver/init/00_create_legacy_sales.sql"

docker compose -f docker-compose.yml up -d legacy-sqlserver

for attempt in $(seq 1 60); do
  if docker exec "$container" bash -lc 'if [ -x /opt/mssql-tools18/bin/sqlcmd ]; then SQLCMD=/opt/mssql-tools18/bin/sqlcmd; else SQLCMD=/opt/mssql-tools/bin/sqlcmd; fi; "$SQLCMD" -C -S localhost -U sa -P "$MSSQL_SA_PASSWORD" -Q "SELECT 1"' >/dev/null 2>&1; then
    break
  fi

  if [ "$attempt" -eq 60 ]; then
    echo "SQL Server did not become ready in time." >&2
    exit 1
  fi

  sleep 2
done

docker exec -i "$container" bash -lc 'if [ -x /opt/mssql-tools18/bin/sqlcmd ]; then SQLCMD=/opt/mssql-tools18/bin/sqlcmd; else SQLCMD=/opt/mssql-tools/bin/sqlcmd; fi; "$SQLCMD" -C -S localhost -U sa -P "$MSSQL_SA_PASSWORD" -d master -i /dev/stdin' < "$init_sql"

echo "Local SQL Server fixture is ready: localhost:${MSSQL_PORT:-1433}, database LegacySales."
