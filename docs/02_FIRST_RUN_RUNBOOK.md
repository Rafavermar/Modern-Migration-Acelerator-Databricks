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

Log in to the Full Trial workspace:

```bash
databricks auth login --host https://<full-trial-workspace-url>
```

Then update `.env`:

```bash
DATABRICKS_PROFILE=DEFAULT
DATABRICKS_BUNDLE_ENV=dev
DATABRICKS_CATALOG=migration_accelerator_dev
DATABRICKS_NODE_TYPE_ID=<available-node-type>
```

Leave `LEGACY_METADATA_SOURCE_ROOT` empty for the first sample run. The bundle will use sample metadata synced with the project.

## 3. Validate the bundle

```bash
bash scripts/validate_bundle.sh
```

This should succeed before any deployment.

## 4. Deploy dev

```bash
bash scripts/deploy_dev.sh
```

Expected result:

- Databricks bundle files are synced to the workspace.
- Two jobs are created: accelerator and target demo.

## 5. Run the accelerator

```bash
bash scripts/run_accelerator_dev.sh
```

Expected Delta outputs:

- `control.run_log`
- `control.metadata_snapshots`
- `bronze.raw_metadata`
- `silver.assets`
- `silver.dependencies`
- `gold.risk_register`
- `gold.target_databricks_blueprint`
- `gold.data_quality_plan`

## 6. Run the target demo

```bash
bash scripts/run_target_demo_dev.sh
```

Expected output:

- `demo.target_migration_plan`

## 7. Move from sample metadata to customer metadata

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

## 8. Decide next phase

After the first successful customer metadata run:

- Review `gold.risk_register`.
- Review `gold.target_databricks_blueprint`.
- Review `gold.data_quality_plan`.
- Decide per source: federation, ingestion, external table, volume or custom connector.
- Add Neo4j only after the Delta graph is correct.

## Stop Conditions

Stop and fix before continuing if:

- CLI still points to Free Edition.
- Unity Catalog is unavailable.
- You cannot create or access the target catalog.
- The selected node type is unavailable.
- The bundle does not validate.
- The accelerator job cannot write Delta tables.
