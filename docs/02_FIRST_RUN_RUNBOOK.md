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
- Three jobs are created: accelerator, target demo and semantic index prep.
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

## 8. Prepare semantic corpus

```bash
bash scripts/run_semantic_index_prep_dev.sh
```

Expected output:

- `gold.semantic_legacy_documents`

This table contains sanitized chunks from source artifacts and generated accelerator outputs. It is the Delta source for Databricks Vector Search. The primary key is `chunk_id`; the text column is `chunk_text`.

## 9. Create Vector Search index

Create the endpoint and Delta Sync index:

```bash
bash scripts/create_vector_search_dev.sh
```

PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\create_vector_search_dev.ps1
```

Default dev configuration:

- endpoint: `mma-vector-search-dev`
- endpoint type: `STANDARD`
- source table: `migration_accelerator_dev.gold.semantic_legacy_documents`
- index: `migration_accelerator_dev.gold.semantic_legacy_documents_vs`
- primary key: `chunk_id`
- embedding source column: `chunk_text`
- embedding endpoint: `databricks-qwen3-embedding-0-6b`
- index subtype: `HYBRID`
- sync mode: `TRIGGERED`

Query the index:

```bash
bash scripts/query_vector_search_dev.sh "Which high risk legacy assets should be migrated first?"
```

PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\query_vector_search_dev.ps1 -Query "Which high risk legacy assets should be migrated first?"
```

This step uses Databricks Vector Search and the embedding model endpoint, so it can consume trial credits. Use `TRIGGERED` sync for controlled dev cost.

The script waits until the index reports `ready=true`, then triggers sync. A first index build can take several minutes because Databricks provisions endpoint and pipeline resources. A successful dev run should show `indexed_row_count` equal to the number of semantic chunks, currently `309` for the demo plus SQL Server export.

Where to see it:

- `Catalog` > `migration_accelerator_dev` > `gold` > `semantic_legacy_documents`: source Delta table.
- `Catalog` search `semantic_legacy_documents_vs`: managed Vector Search index.
- Vector index page > `Overview` > `Data Ingest`: sync status and `Sync now`.
- CLI/API: `databricks --profile <profile> vector-search-endpoints get-endpoint mma-vector-search-dev`.

It is normal that `mma-vector-search-dev` does not appear under `AI/ML > Serving`. Vector Search endpoints are not standard Model Serving endpoints. The embedding model endpoint is Databricks-managed and may appear under AI Gateway or foundation model areas depending on workspace UI and filters.

## 10. Run RAG-ready search utility

After Vector Search returns useful results, build a local retrieval brief:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\rag_search_dev.ps1 -Question "Which order assets need the first migration review?"
```

Git Bash equivalent:

```bash
bash scripts/rag_search_dev.sh "Which order assets need the first migration review?"
```

Expected local outputs:

- `local_outputs/rag/latest_search.json`: raw Vector Search rows and response.
- `local_outputs/rag/latest_answer.md`: readable evidence brief for a migration reviewer.
- `local_outputs/rag/latest_trace.json`: trace-shaped payload for later MLflow GenAI evaluation.

This is not yet an autonomous assistant. It retrieves evidence and builds a deterministic brief so the team can validate retrieval quality before adding an LLM.

Optional MLflow starter logging:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup_dev_env.ps1 -InstallGenAiDeps
powershell -ExecutionPolicy Bypass -File .\scripts\rag_search_dev.ps1 -Question "Which order assets need the first migration review?" -LogMlflow
```

The MLflow run logs the query, retrieved chunk count and local artifacts to `MLFLOW_EXPERIMENT_NAME`. Full MLflow GenAI tracing and scorer-based evaluation should be added when an LLM-generated response is introduced.

## 11. Publish to Neo4j

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

## 12. Move from sample metadata to customer metadata

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

Customer mode keeps the same execution commands. The only functional change is the metadata source path:

```bash
bash scripts/validate_bundle.sh
bash scripts/deploy_dev.sh
bash scripts/run_accelerator_dev.sh
bash scripts/run_target_demo_dev.sh
bash scripts/run_semantic_index_prep_dev.sh
bash scripts/create_vector_search_dev.sh
```

Then publish graph exploration from the same normalized model:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\publish_neo4j_graph.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\verify_neo4j_graph.ps1
```

## 13. Known first-run fixes

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

Issue: `databricks vector-search-indexes query-index` returns an unmarshalling error even when the REST API returns `200 OK`.

Cause: CLI wrapper issue in the current Databricks CLI build.

Fix: query scripts use `databricks api post /api/2.0/vector-search/indexes/<index>/query` with the same request body.

Issue: `databricks api post /api/...` returns `Not Found` from Git Bash on Windows.

Cause: Git Bash path conversion rewrites `/api/...` as a Windows path.

Fix: Vector Search Bash scripts export `MSYS_NO_PATHCONV=1` and `MSYS2_ARG_CONV_EXCL=*`.

## 14. Decide next phase

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
