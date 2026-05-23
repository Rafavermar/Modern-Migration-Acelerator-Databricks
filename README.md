# Modern Migration Accelerator for Databricks

Plug-and-play migration assessment accelerator for Databricks modernization.

The solution parses legacy metadata, normalizes assets, builds a dependency graph, generates migration risk outputs, produces Databricks target blueprints and writes Delta tables in Databricks.

## How it works

1. Configure the repo once for a Databricks Full Trial or full workspace.
2. Run with the included sample estate copied to a Unity Catalog volume to prove the platform path.
3. Point `LEGACY_METADATA_SOURCE_ROOT` to customer exports from ADF, Synapse, SQL Server, notebooks, SQL scripts and documentation.
4. Run the bundle again to produce Delta outputs for assessment, graph exploration and migration planning.
5. Publish the graph to Neo4j and prepare semantic chunks for Databricks Vector Search when the first Delta outputs are trusted.

The customer does not need to use an existing metadata framework. The framework in this repo is the normalization contract used by the accelerator. A customer can provide raw exported artifacts in the landing folder, and the accelerator maps them into `bronze`, `silver`, `gold` and `control` outputs.

## Plug-and-play connection points

Change only these inputs when moving from demo to a real customer estate:

| Area | Demo default | Customer value |
| --- | --- | --- |
| Databricks workspace | `DATABRICKS_PROFILE=mma-fulltrial` | Customer CLI profile or approved service principal. |
| Target catalog | `migration_accelerator_dev` | Customer Unity Catalog catalog. |
| Metadata landing | `/Volumes/<catalog>/landing/legacy_metadata/demo` | `/Volumes/<catalog>/landing/legacy_metadata/` or an approved external volume. |
| ADF and Synapse artifacts | `samples/legacy_metadata/` | Exported `.json`, `.csv`, `.sql` and `.ipynb` files under the landing folders. |
| SQL Server | Docker fixture plus `local_outputs/legacy_metadata/sqlserver_inventory.csv` | Read-only metadata export saved under `sqlserver/inventory/`, or approved federation/connector access. |
| Neo4j | Local `.env` AuraDB values | Customer AuraDB or Neo4j endpoint and secret strategy. |

Recommended customer landing folders:

```text
/Volumes/<catalog>/landing/legacy_metadata/adf/
/Volumes/<catalog>/landing/legacy_metadata/synapse/inventory/
/Volumes/<catalog>/landing/legacy_metadata/synapse/notebooks/
/Volumes/<catalog>/landing/legacy_metadata/synapse/sql/
/Volumes/<catalog>/landing/legacy_metadata/sqlserver/inventory/
/Volumes/<catalog>/landing/legacy_metadata/docs/
```

## Solution scope

Included now:

- Databricks Declarative Automation Bundle with dev target.
- Manual validation, deployment and run scripts.
- Sample legacy metadata for a first Databricks run.
- Local SQL Server Docker fixture for repeatable legacy metadata extraction tests.
- Self-contained serverless Python tasks for reliable Databricks execution.
- Python/Spark pipeline for metadata normalization, graph-ready Delta outputs and gold assessment outputs.
- Semantic Delta corpus preparation for Databricks Vector Search.
- Delta outputs for bronze, silver, gold and control layers.

Full solution technologies:

- Databricks Workflows on serverless compute and Delta tables for the assessment backbone.
- Neo4j AuraDB for graph exploration and impact analysis.
- Databricks Vector Search.
- RAG/search over legacy artifacts and generated blueprints.
- MLflow Tracking or MLflow Tracing.
- Databricks Model Serving.
- Enterprise CI/CD integration through the customer standard toolchain.

The first deploy validates the Databricks assessment backbone. Neo4j, Vector Search and MLflow are activated as soon as the Full Trial workspace and AuraDB credentials are available.

## Outputs

The required audit and gold outputs are:

- `control.run_log`
- `control.metadata_snapshots`
- `gold.assessment_summary`
- `gold.asset_priority_matrix`
- `gold.graph_edges`
- `gold.risk_register`
- `gold.semantic_legacy_documents`
- `gold.target_databricks_blueprint`
- `gold.data_quality_plan`

The accelerator also writes internal Delta tables:

- `bronze.raw_metadata`
- `silver.assets`
- `silver.dependencies`

Read the assessment results in this order:

1. `gold.assessment_summary` for the one-row executive view.
2. `gold.asset_priority_matrix` for the review backlog.
3. `gold.graph_edges` for readable dependency relationships.
4. `gold.risk_register` for risk detail.
5. `gold.target_databricks_blueprint` for target pattern decisions.
6. `gold.data_quality_plan` for validation work.
7. `gold.semantic_legacy_documents` for Vector Search indexing.

By default the catalog is `migration_accelerator_dev`. Override it with `DATABRICKS_CATALOG` in `.env`.

## Repository setup

Copy the sample environment file and fill only the values you need:

```bash
cp .env.example .env
```

Create the local Python environment:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup_dev_env.ps1
```

If you are already in Git Bash or Linux/macOS:

```bash
bash scripts/setup_dev_env.sh
```

On Windows, use Git Bash from `C:\Program Files\Git\bin\bash.exe` for the required `scripts/*.sh` files. The Windows `bash` command can point to WSL; if WSL has no distro installed, call Git Bash explicitly:

```powershell
& 'C:\Program Files\Git\bin\bash.exe' scripts/local_smoke_test.sh
```

Preferred authentication is a Databricks CLI profile. Use the workspace URL from the browser, not only the numeric workspace ID:

```bash
databricks auth login --host https://your-workspace-url --profile mma-fulltrial
```

Then set this in `.env`:

```bash
DATABRICKS_PROFILE=mma-fulltrial
DATABRICKS_WORKSPACE_ID=<workspace-id>
DATABRICKS_CATALOG=migration_accelerator_dev
```

Do not commit `.env`; it is ignored by Git.

Keep credentials out of committed sample files. Use `.env` for local development, Databricks secrets for deployed jobs and customer secret managers for enterprise implementations.
The Bash scripts load `.env` without shell-evaluating secret values, so passwords can contain normal special characters.

For Neo4j AuraDB, put the values in local `.env`:

```bash
NEO4J_URI=<neo4j+s://host.databases.neo4j.io>
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=<paste locally only>
NEO4J_DATABASE=neo4j
AURA_INSTANCEID=<aura-instance-id>
AURA_INSTANCENAME=<aura-instance-name>
```

Install the graph dependency and verify connectivity:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup_dev_env.ps1 -InstallGraphDeps
powershell -ExecutionPolicy Bypass -File .\scripts\check_neo4j_connection.ps1
```

## Local checks before cloud deploy

Use the local checks while the Full Trial and Neo4j AuraDB accounts are being created:

```bash
bash scripts/local_smoke_test.sh
```

On Windows PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\local_smoke_test.ps1
```

This validates Python syntax, unit tests and sample metadata parsing without calling Databricks.

When the Full Trial exists, follow `docs/02_FIRST_RUN_RUNBOOK.md`. It includes the preflight checks, bundle validation, deployment order and first-run acceptance criteria.

The local sample estate now includes:

- ADF pipelines.
- ADF datasets, linked services and triggers.
- Synapse dedicated SQL tables.
- Synapse serverless database inventory.
- Synapse external tables.
- Synapse notebook sample.
- SQL scripts and dependencies.

For real customer implementations, use `docs/01_CUSTOMER_IMPLEMENTATION.md` as the operating model. The customer exports metadata into a governed landing area; the accelerator consumes those exports and generates the dependency graph, risk register and target blueprint.

Use `docs/00_PRODUCT_POSITIONING.md` to decide when this accelerator is appropriate, when existing tools are better, and how to choose between federation, ingestion, external tables and volumes.

The lightweight metadata taxonomy is documented in `docs/03_METADATA_FRAMEWORK.md` and represented by `contracts/metadata_taxonomy.json`.

## Local SQL Server fixture

SQL Server in Docker is prepared as a local fixture so we can simulate a legacy SQL Server source before the cloud accounts are ready.

Start and seed it:

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

On Windows PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\check_sqlserver_fixture.ps1
```

Inspect objects and sample rows without SSMS:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\query_sqlserver_fixture.ps1
```

Run an ad hoc query:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\query_sqlserver_fixture.ps1 -Query "SELECT TOP (10) * FROM mart.FactOrders"
```

Export inventory metadata:

```bash
bash scripts/export_sqlserver_metadata.sh
```

On Windows PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\export_sqlserver_metadata.ps1
```

The export goes to:

```text
local_outputs/legacy_metadata/sqlserver_inventory.csv
```

More detail is in `docs/04_LOCAL_SQLSERVER_FIXTURE.md`.

The SQL Server container is a developer fixture. In a real customer implementation, SQL Server metadata should usually be exported with approved read-only catalog queries and delivered to the metadata landing area.

## Full Databricks trial timing

Start the full Databricks trial when you are ready to run:

```bash
bash scripts/validate_bundle.sh
bash scripts/deploy_dev.sh
bash scripts/run_accelerator_dev.sh
```

You do not need the trial just to review, edit or run local smoke tests. You do need it for end-to-end validation because the accelerator writes Delta tables, creates Databricks jobs and expects a real Databricks workspace, not Databricks Free Edition.

Before the first full run, have these ready:

- Databricks workspace URL and CLI authentication.
- Unity Catalog permissions to create or use the target catalog and schemas.
- Legacy metadata exports, or use the included sample files for the first smoke test.

The default bundle jobs use Databricks serverless compute and self-contained Python script tasks. Customer workspaces can replace this with classic job clusters if their policies require it.

Run the non-deploying preflight first:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\preflight_full_trial.ps1
```

Or with Git Bash:

```bash
bash scripts/preflight_full_trial.sh
```

For the demo run, leave `LEGACY_METADATA_SOURCE_ROOT` empty. `scripts/run_accelerator_dev.sh` creates the `landing` schema and `legacy_metadata` managed volume if needed, then uploads `samples/legacy_metadata` to:

```text
/Volumes/migration_accelerator_dev/landing/legacy_metadata/demo
```

For customer metadata, upload files to a Unity Catalog volume and set:

```bash
LEGACY_METADATA_SOURCE_ROOT=/Volumes/migration_accelerator_dev/landing/legacy_metadata
```

Supported file types are `.json` for ADF-like exports, `.csv` for Synapse or SQL Server inventory extracts, `.ipynb` for notebooks and `.sql` for SQL scripts.

## Neo4j timing

Create **Neo4j AuraDB Professional - Free trial** for the first graph integration test. A 4GB vector-optimized instance is fine when you want to avoid friction for later graph plus vector experiments.

Use the accelerator graph outputs first, then publish them to AuraDB. The needed information is:

- Neo4j URI.
- Database name.
- Authentication method and secret location.
- TLS requirement.
- Network access path from Databricks to Neo4j.
- Decision on read-only graph publishing versus bidirectional sync.

The dependency graph is stored in `silver.dependencies` and exposed for users in `gold.graph_edges`.

Publish and verify the graph locally:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\publish_neo4j_graph.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\verify_neo4j_graph.ps1
```

Git Bash equivalent:

```bash
bash scripts/publish_neo4j_graph.sh
bash scripts/verify_neo4j_graph.sh
```

The publisher reads `samples/legacy_metadata` and also `local_outputs/legacy_metadata` when the SQL Server fixture has been exported. It creates `MigrationRun`, `MigrationAsset`, `SourceSystem`, `TargetPattern` and `MIGRATION_DEPENDENCY` records in Neo4j.

The Neo4j workflow is documented in `docs/05_ADVANCED_CAPABILITIES.md`.

## Manual Databricks commands

Validate the bundle:

```bash
bash scripts/validate_bundle.sh
```

Deploy the dev bundle:

```bash
bash scripts/deploy_dev.sh
```

This also prepares the Unity Catalog landing volume and uploads runtime Python scripts under `/Volumes/<catalog>/landing/legacy_metadata/runtime`.

Run the accelerator:

```bash
bash scripts/run_accelerator_dev.sh
```

If `LEGACY_METADATA_SOURCE_ROOT` is empty, this command first refreshes the demo metadata under `/Volumes/<catalog>/landing/legacy_metadata/demo`. If it is set, the job reads the customer landing path and does not upload samples.
If `local_outputs/legacy_metadata` exists from the SQL Server fixture, it is uploaded into the same demo metadata root.

Create the target demo table from the generated blueprint:

```bash
bash scripts/run_target_demo_dev.sh
```

The target demo writes:

- `demo.target_migration_plan`

Prepare the semantic corpus for Vector Search:

```bash
bash scripts/run_semantic_index_prep_dev.sh
```

This writes `gold.semantic_legacy_documents` with primary key `chunk_id` and text column `chunk_text`. The table has Delta Change Data Feed enabled so it can become the source for a Vector Search Delta Sync index.

Create and query the Vector Search endpoint and Delta Sync index:

```bash
bash scripts/create_vector_search_dev.sh
bash scripts/query_vector_search_dev.sh "Which high risk assets should be migrated first?"
```

PowerShell equivalent:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\create_vector_search_dev.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\query_vector_search_dev.ps1 -Query "Which high risk assets should be migrated first?"
```

Default dev settings:

- endpoint: `mma-vector-search-dev`
- endpoint type: `STANDARD`
- source table: `migration_accelerator_dev.gold.semantic_legacy_documents`
- index: `migration_accelerator_dev.gold.semantic_legacy_documents_vs`
- primary key: `chunk_id`
- embedding source column: `chunk_text`
- embedding endpoint: `databricks-qwen3-embedding-0-6b`
- sync mode: `TRIGGERED`

The query scripts call the Vector Search REST endpoint through `databricks api post` because the current CLI wrapper can print an unmarshalling error even when the API returns valid results.

In the Databricks UI, inspect the Vector Search index through `Catalog`, not `AI/ML > Serving`. Search for `semantic_legacy_documents_vs` or browse `migration_accelerator_dev.gold`. The Vector Search endpoint is managed separately from standard Model Serving endpoints.

Build a RAG-ready retrieval brief:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\rag_search_dev.ps1 -Question "Which order assets need the first migration review?"
```

This writes:

- `local_outputs/rag/latest_search.json`
- `local_outputs/rag/latest_answer.md`
- `local_outputs/rag/latest_trace.json`

The starter utility does retrieval and grounded summarization only. Add `-LogMlflow` after installing `pip install -e .[genai]` to log the run artifacts to the configured MLflow experiment.

On Windows, Databricks bundle scripts are Bash-first because the package includes `scripts/*.sh`. Use Git Bash or WSL for those scripts, or run equivalent `databricks bundle ...` commands directly from PowerShell after the Full Trial CLI profile is configured.

## CI/CD readiness

This project is packaged as a Databricks Declarative Automation Bundle and is therefore ready to be integrated into enterprise CI/CD. CI/CD workflow files are intentionally excluded from the repo because authentication, approval gates, environments, service principals and deployment policies are customer-specific.

Optional future files:

- `.github/workflows/databricks-bundle-dev.yml`
- `azure-pipelines.yml`

Do not create those files unless explicitly requested.

## Documentation

Read these in order:

- `docs/00_PRODUCT_POSITIONING.md`
- `docs/01_CUSTOMER_IMPLEMENTATION.md`
- `docs/02_FIRST_RUN_RUNBOOK.md`
- `docs/06_REPOSITORY_ARCHITECTURE.md`
- `contracts/customer_intake_checklist.md`
- `docs/03_METADATA_FRAMEWORK.md`
- `docs/04_LOCAL_SQLSERVER_FIXTURE.md`
- `docs/05_ADVANCED_CAPABILITIES.md`

Vector Search, embeddings, RAG, MLflow tracking, GenAI tracing and model or agent evaluation are full-solution layers that build on the trusted Databricks assessment outputs.
