# Local SQL Server Fixture

This fixture is for local preparation only. It does not replace the Databricks Full Trial run.

## Purpose

- Simulate a small legacy SQL Server estate.
- Generate metadata inventory that follows the same CSV shape as the Synapse sample inventory.
- Let the accelerator parser be tested before Databricks and Neo4j accounts are ready.

## Start the fixture

Create `.env` from `.env.example`, then set the local SQL Server password variable there. Do not commit `.env`.

Start and seed SQL Server:

```bash
bash scripts/bootstrap_sqlserver.sh
```

On Windows PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\bootstrap_sqlserver.ps1
```

This starts `mcr.microsoft.com/mssql/server:2022-latest`, creates the `LegacySales` database and seeds:

- `dbo.CustomerOrders`
- `dbo.Customers`
- `mart.DimCustomer`
- `mart.FactOrders`
- `dbo.usp_build_fact_orders`

## Export metadata

```bash
bash scripts/export_sqlserver_metadata.sh
```

On Windows PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\export_sqlserver_metadata.ps1
```

The export is written to:

```text
local_outputs/legacy_metadata/sqlserver_inventory.csv
```

You can later point the accelerator to that folder with:

```bash
LEGACY_METADATA_SOURCE_ROOT=local_outputs/legacy_metadata
```

## Boundary

SQL Server in Docker is a local fixture for repeatable development. Synapse serverless databases, external tables and notebooks are represented by files under `samples/legacy_metadata`; they are not executed inside the SQL Server container.
