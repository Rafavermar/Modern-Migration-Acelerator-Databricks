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
DATABRICKS_WORKSPACE_ID=7474660420173503
DATABRICKS_BUNDLE_ENV=dev
DATABRICKS_CATALOG=migration_accelerator_dev
DATABRICKS_NODE_TYPE_ID=<available-node-type>
```

Leave `LEGACY_METADATA_SOURCE_ROOT` empty for the first sample run. The bundle will use sample metadata synced with the project.

## 3. Configure Neo4j locally

Put the AuraDB values in `.env`. Keep the password local only.

```bash
NEO4J_URI=neo4j+s://9c447469.databases.neo4j.io
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=<paste locally only>
NEO4J_DATABASE=neo4j
AURA_INSTANCEID=9c447469
AURA_INSTANCENAME=mma-graph-dev
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

## 5. Deploy dev

```bash
bash scripts/deploy_dev.sh
```

Expected result:

- Databricks bundle files are synced to the workspace.
- Two jobs are created: accelerator and target demo.

## 6. Run the accelerator

```bash
bash scripts/run_accelerator_dev.sh
```

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

## 8. Move from sample metadata to customer metadata

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

## 9. Decide next phase

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
- The selected node type is unavailable.
- The bundle does not validate.
- The accelerator job cannot write Delta tables.
