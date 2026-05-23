# First Run Runbook

Use this runbook when the Full Trial Databricks workspace is ready.

Do not run deployment commands against Databricks Free Edition.

## 1. Confirm local readiness

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup_dev_env.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\preflight_full_trial.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\local_smoke_test.ps1
```

Git Bash equivalent:

```bash
bash scripts/setup_dev_env.sh
bash scripts/preflight_full_trial.sh
bash scripts/local_smoke_test.sh
```

## 2. Configure Databricks CLI

Log in to the Full Trial workspace. Use the workspace URL from the browser; the numeric workspace ID alone is not enough for CLI login.

```bash
databricks auth login --host https://<full-trial-workspace-url> --profile mma-fulltrial
```

Then update `.env`:

```bash
DATABRICKS_PROFILE=mma-fulltrial
DATABRICKS_WORKSPACE_ID=<workspace-id>
DATABRICKS_BUNDLE_ENV=dev
DATABRICKS_CATALOG=migration_accelerator_dev
```

Leave `LEGACY_METADATA_SOURCE_ROOT` empty for the first sample run. The run script will create the `landing` schema and `legacy_metadata` managed volume if needed, then upload `samples/legacy_metadata` to:

```text
/Volumes/migration_accelerator_dev/landing/legacy_metadata/demo
```

The bundle jobs use Databricks serverless compute and self-contained Python script tasks by default. No node type is required for the Full Trial workspace.

## 3. Configure Neo4j locally

Put the AuraDB values in `.env`. Keep the password local only.

```bash
NEO4J_URI=<neo4j+s://host.databases.neo4j.io>
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=<paste locally only>
NEO4J_DATABASE=neo4j
AURA_INSTANCEID=<aura-instance-id>
AURA_INSTANCENAME=<aura-instance-name>
```

Install the graph dependency and test the connection:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup_dev_env.ps1 -InstallGraphDeps
powershell -ExecutionPolicy Bypass -File .\scripts\check_neo4j_connection.ps1
```

The first Databricks run validates the Delta assessment backbone. Graph publishing follows once `gold.graph_edges` is trusted, and the AuraDB connection should already be known and validated.

## 4. Validate the bundle

```bash
bash scripts/validate_bundle.sh
```

This should succeed before any deployment.

If deploy fails with `openpgp: key expired` while downloading Terraform, update Databricks CLI and log in again:

```powershell
winget upgrade --id Databricks.DatabricksCLI --exact --source winget --accept-package-agreements --accept-source-agreements
databricks auth login --host https://<full-trial-workspace-url> --profile mma-fulltrial
```

The bundle should not use `/Workspace/.../.bundle/.../files` as metadata input. That path is for synced code. Metadata input should be in `/Volumes/<catalog>/landing/legacy_metadata/demo` for demo runs or another Unity Catalog volume path for customer runs.

## 5. Deploy dev

```bash
bash scripts/deploy_dev.sh
```

Expected result:

- Databricks bundle files are synced to the workspace.
- Two jobs are created: accelerator and target demo.
- Runtime Python scripts are uploaded to `/Volumes/<catalog>/landing/legacy_metadata/runtime`.

## 6. Run the accelerator

```bash
bash scripts/run_accelerator_dev.sh
```

What this does:

- If `LEGACY_METADATA_SOURCE_ROOT` is empty, upload demo files from `samples/legacy_metadata` to `/Volumes/<catalog>/landing/legacy_metadata/demo`.
- If `local_outputs/legacy_metadata` exists from the SQL Server fixture, upload those files into the same demo root.
- Start the deployed Databricks job.
- Read metadata with Spark `binaryFile` from the configured source path.
- Write control, bronze, silver and gold Delta tables.

Expected Delta outputs:

- `control.run_log`
- `control.metadata_snapshots`
- `bronze.raw_metadata`
- `silver.assets`
- `silver.dependencies`
- `gold.assessment_summary`
- `gold.asset_priority_matrix`
- `gold.graph_edges`
- `gold.risk_register`
- `gold.target_databricks_blueprint`
- `gold.data_quality_plan`

First review query order:

```sql
SELECT * FROM gold.assessment_summary;
SELECT * FROM gold.asset_priority_matrix ORDER BY review_priority, risk_score DESC;
SELECT * FROM gold.graph_edges;
```

## 7. Run the target demo

```bash
bash scripts/run_target_demo_dev.sh
```

Expected output:

- `demo.target_migration_plan`

## 8. Publish to Neo4j

Check AuraDB connectivity:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\check_neo4j_connection.ps1
```

Publish the graph:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\publish_neo4j_graph.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\verify_neo4j_graph.ps1
```

Git Bash equivalent:

```bash
bash scripts/publish_neo4j_graph.sh
bash scripts/verify_neo4j_graph.sh
```

Expected demo result after SQL Server fixture export:

- `52` `MigrationAsset` nodes.
- `37` `MIGRATION_DEPENDENCY` relationships.
- `4` `SourceSystem` nodes.
- `13` `TargetPattern` nodes.

Neo4j Browser starter query:

```cypher
MATCH (r:MigrationRun)-[:INCLUDES_ASSET]->(a:MigrationAsset)
RETURN r, a
LIMIT 50;
```

Impact query:

```cypher
MATCH path = (a:MigrationAsset)-[:MIGRATION_DEPENDENCY*1..3]->(b:MigrationAsset)
WHERE a.asset_name CONTAINS 'FactOrders'
RETURN path
LIMIT 25;
```

## 9. Move from sample metadata to customer metadata

Create or select a governed landing volume:

```text
/Volumes/<catalog>/landing/legacy_metadata/
```

Upload customer exports using the landing contract in `docs/01_CUSTOMER_IMPLEMENTATION.md`.

Then set:

```bash
LEGACY_METADATA_SOURCE_ROOT=/Volumes/<catalog>/landing/legacy_metadata
```

Redeploy or rerun with the updated bundle variable.

Put customer artifacts under the same root, for example:

```text
/Volumes/<catalog>/landing/legacy_metadata/adf/
/Volumes/<catalog>/landing/legacy_metadata/synapse/inventory/
/Volumes/<catalog>/landing/legacy_metadata/synapse/notebooks/
/Volumes/<catalog>/landing/legacy_metadata/synapse/sql/
/Volumes/<catalog>/landing/legacy_metadata/sqlserver/inventory/
```

For SQL Server, the easiest first implementation is export-only discovery: run the approved metadata query in `samples/sqlserver/extract/metadata_inventory.sql`, save the CSV under `sqlserver/inventory/`, then run the accelerator.

## 10. Known first-run fixes

Issue: `OSError: [Errno 5] Input/output error` while reading files under `/Workspace/Users/.../.bundle/.../files/samples/legacy_metadata`.

Cause: Workspace Files are reliable for bundle code but should not be used as the functional metadata landing area for serverless jobs.

Fix: keep code in the bundle, upload metadata to a Unity Catalog volume, and point `source_root` there. Demo runs now use `/Volumes/<catalog>/landing/legacy_metadata/demo` automatically.

Issue: `Public DBFS root is disabled. Access is denied on path: /tmp/...`.

Cause: the workspace blocks public DBFS root, which is common in governed workspaces.

Fix: use Unity Catalog volumes for metadata landing. The scripts now create/use `${DATABRICKS_CATALOG}.landing.legacy_metadata`.

Issue: `No FileSystem for scheme "C"` when using Git Bash on Windows.

Cause: Git Bash path conversion changed `/Volumes/...` into a Windows path before invoking the Databricks CLI.

Fix: the Databricks Bash scripts export `MSYS_NO_PATHCONV=1` and `MSYS2_ARG_CONV_EXCL=*` before calling the CLI.

Issue: intermittent `OSError: [Errno 5] Input/output error` while opening the Python task file under Workspace Files.

Cause: serverless task startup can hit transient Workspace Files reads.

Fix: the jobs execute runtime Python scripts from the Unity Catalog volume instead of `/Workspace/.../.bundle/.../files`.

## 11. Decide next phase

After the first successful customer metadata run:

- Review `gold.risk_register`.
- Review `gold.target_databricks_blueprint`.
- Review `gold.data_quality_plan`.
- Decide per source: federation, ingestion, external table, volume or custom connector.
- Publish to Neo4j after the Delta graph is correct.
- Add Vector Search over raw artifacts and generated outputs.
- Add MLflow tracing/evaluation when GenAI or generated recommendations enter the flow.

## Stop Conditions

Stop and fix before continuing if:

- CLI still points to Free Edition.
- Unity Catalog is unavailable.
- You cannot create or access the target catalog.
- The bundle does not validate.
- The accelerator job cannot write Delta tables.
