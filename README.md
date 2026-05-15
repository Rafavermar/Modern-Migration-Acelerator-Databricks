# Modern Migration Accelerator for Databricks

MVP scaffold for a Databricks-based data engineering and migration analysis accelerator.

The MVP parses legacy metadata, normalizes assets, builds a dependency graph, generates migration risk outputs, produces Databricks target blueprints and writes Delta tables in Databricks.

## MVP scope

Included now:

- Databricks Declarative Automation Bundle with dev target.
- Manual validation, deployment and run scripts.
- Sample legacy metadata for a first Databricks run.
- Local SQL Server Docker fixture for repeatable legacy metadata extraction tests.
- Python/Spark pipeline with no mandatory MLflow, Vector Search, GenAI or Neo4j dependency.
- Delta outputs for bronze, silver, gold and control layers.

Deferred from the first deterministic build, but still planned for the full product:

- Databricks Vector Search.
- MLflow Tracking or MLflow Tracing.
- Databricks Model Serving.
- GitHub Actions, Azure DevOps or Jenkins automation.
- Neo4j runtime integration.

Those capabilities are intentionally staged so the core accelerator is built and tested step by step.

## Outputs

The required MVP audit and gold outputs are:

- `control.run_log`
- `control.metadata_snapshots`
- `gold.risk_register`
- `gold.target_databricks_blueprint`
- `gold.data_quality_plan`

The accelerator also writes internal Delta tables:

- `bronze.raw_metadata`
- `silver.assets`
- `silver.dependencies`

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

Preferred authentication is a Databricks CLI profile:

```bash
databricks auth login --host https://your-workspace-url
```

Then set this in `.env`:

```bash
DATABRICKS_PROFILE=DEFAULT
DATABRICKS_CATALOG=migration_accelerator_dev
```

Do not commit `.env`; it is ignored by Git.

## Current local-only workflow

The Databricks CLI currently points to Databricks Free Edition, so do not deploy the bundle yet.

Use the local checks while the Full Trial and Neo4j accounts are not ready:

```bash
bash scripts/local_smoke_test.sh
```

On Windows PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\local_smoke_test.ps1
```

This validates Python syntax, unit tests and sample metadata parsing without calling Databricks.

The local sample estate now includes:

- ADF pipelines.
- Synapse dedicated SQL tables.
- Synapse serverless database inventory.
- Synapse external tables.
- Synapse notebook sample.
- SQL scripts and dependencies.

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

More detail is in `docs/LOCAL_SQLSERVER_FIXTURE.md`.

## Full Databricks trial timing

Start the full Databricks trial when you are ready to run:

```bash
bash scripts/validate_bundle.sh
bash scripts/deploy_dev.sh
bash scripts/run_accelerator_dev.sh
```

You do not need the trial just to review, edit or run local smoke tests. You do need it for end-to-end validation because the MVP writes Delta tables, creates Databricks jobs and expects a real Databricks workspace, not Databricks Free Edition.

Before the first full run, have these ready:

- Databricks workspace URL and CLI authentication.
- Unity Catalog permissions to create or use the target catalog and schemas.
- A small available job cluster node type. The default is `Standard_DS3_v2`; override `DATABRICKS_NODE_TYPE_ID` if your workspace uses another node.
- Legacy metadata exports, or use the included sample files for the first smoke test.

For real metadata, upload files to a Unity Catalog volume and set:

```bash
LEGACY_METADATA_SOURCE_ROOT=/Volumes/migration_accelerator_dev/landing/legacy_metadata
```

Supported MVP file types are `.json` for ADF-like exports, `.csv` for Synapse inventory extracts and `.sql` for SQL scripts.

## Neo4j timing

Neo4j connection information is not needed for the MVP.

Provide Neo4j details only when we add the optional external graph extension after the Delta dependency graph is working. At that point the needed information will be:

- Neo4j URI.
- Database name.
- Authentication method and secret location.
- TLS requirement.
- Network access path from Databricks to Neo4j.
- Decision on read-only graph export versus bidirectional sync.

For now, the dependency graph is stored in `silver.dependencies` and consumed by `gold.risk_register`.

The Neo4j extension plan is documented in `docs/PHASE_2_NEO4J_GRAPH.md`.

## Manual Databricks commands

Validate the bundle:

```bash
bash scripts/validate_bundle.sh
```

Deploy the dev bundle:

```bash
bash scripts/deploy_dev.sh
```

Run the accelerator:

```bash
bash scripts/run_accelerator_dev.sh
```

Create the target demo table from the generated blueprint:

```bash
bash scripts/run_target_demo_dev.sh
```

The target demo writes:

- `demo.target_migration_plan`

On Windows, Databricks bundle scripts are Bash-first because the MVP requires `scripts/*.sh`. Use Git Bash or WSL for those scripts, or run equivalent `databricks bundle ...` commands directly from PowerShell after the Full Trial CLI profile is configured.

## CI/CD readiness

This project is packaged as a Databricks Declarative Automation Bundle and is therefore ready to be integrated into enterprise CI/CD. CI/CD workflow files are intentionally excluded from the MVP because authentication, approval gates, environments, service principals and deployment policies are customer-specific.

Optional future files:

- `.github/workflows/databricks-bundle-dev.yml`
- `azure-pipelines.yml`

Do not create those files unless explicitly requested.

## Phase 2 roadmap

Documented future extensions:

- `docs/PHASE_2_VECTOR_SEARCH.md`
- `docs/PHASE_2_MLFLOW_OBSERVABILITY.md`
- `docs/PHASE_2_NEO4J_GRAPH.md`

Vector Search, embeddings, RAG, MLflow tracking, GenAI tracing and model or agent evaluation should be added only after the deterministic migration analysis MVP is working in Databricks.
