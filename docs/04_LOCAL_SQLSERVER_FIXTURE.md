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

Verify seeded row counts:

```bash
bash scripts/check_sqlserver_fixture.sh
```

Windows:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\check_sqlserver_fixture.ps1
```

Inspect SQL Server objects and sample rows without installing SSMS:

```bash
bash scripts/query_sqlserver_fixture.sh
```

Windows:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\query_sqlserver_fixture.ps1
```

Run an ad hoc query:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\query_sqlserver_fixture.ps1 -Query "SELECT TOP (10) * FROM mart.FactOrders"
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

When `LEGACY_METADATA_SOURCE_ROOT` is empty, `scripts/run_accelerator_dev.sh` uploads this folder into the demo metadata volume together with `samples/legacy_metadata`.

You can later point the accelerator to that folder with:

```bash
LEGACY_METADATA_SOURCE_ROOT=local_outputs/legacy_metadata
```

## Boundary

SQL Server in Docker is a local fixture for repeatable development. Synapse serverless databases, external tables and notebooks are represented by files under `samples/legacy_metadata`; they are not executed inside the SQL Server container.

## Real SQL Server source

In a customer implementation, do not require Docker. Use the same metadata contract with a real source:

1. Customer DBA reviews `samples/sqlserver/extract/metadata_inventory.sql`.
2. Customer runs the query with read-only metadata permissions.
3. Output is saved as CSV under the landing path:

```text
/Volumes/<catalog>/landing/legacy_metadata/sqlserver/inventory/
```

4. The accelerator reads that export with the rest of the ADF, Synapse, notebook and SQL artifacts.

Direct SQL Server connectivity is useful for federation, validation or automated discovery, but export-only onboarding is the simplest first path.
