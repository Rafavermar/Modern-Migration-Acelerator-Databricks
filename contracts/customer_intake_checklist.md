# Customer Intake Checklist

Use this checklist before the first real customer metadata run.

## Product Fit

- Databricks is the target assessment platform.
- The customer needs migration assessment, not only live source querying.
- Existing catalog tools do not already provide a migration-ready Databricks blueprint.
- Metadata exports can be provided without production data movement.

## Databricks

- Full Trial or full workspace available.
- Unity Catalog enabled.
- Workspace URL known.
- CLI profile configured.
- Target catalog name agreed.
- Permissions confirmed for catalog, schema and Delta table creation.
- Job cluster node type confirmed.

## Metadata Landing

- Landing root agreed.
- ADF export folder agreed.
- Synapse inventory folder agreed.
- Synapse notebook folder agreed.
- Synapse SQL folder agreed.
- SQL Server inventory folder agreed, if applicable.
- Documentation folder agreed, if applicable.

## Source Metadata

- ADF pipelines exported.
- ADF datasets exported.
- ADF linked services exported with secrets removed or redacted.
- ADF triggers exported where schedules matter.
- Synapse dedicated pool inventory exported.
- Synapse serverless database inventory exported.
- External table DDL or inventory exported.
- Synapse notebooks exported.
- SQL scripts, procedures and views exported.
- SQL Server inventory exported from read-only metadata queries, if applicable.

## Security

- No production passwords in metadata files.
- Secret storage strategy agreed for future connectivity.
- Network requirements documented.
- Data handling restrictions documented.
- Source owners identified.

## First Run Acceptance

- `control.run_log` has a successful run.
- `silver.assets` contains expected source systems.
- `silver.dependencies` contains expected relationships.
- `gold.risk_register` is reviewable by the migration team.
- `gold.target_databricks_blueprint` contains actionable target patterns.
- `gold.data_quality_plan` contains validation work items.
