# Customer Implementation Guide

This accelerator should be treated as a deployable product, not as a folder of examples.

The customer does not copy this repository into every legacy system. The implementation team deploys the repository once, then the customer provides exports and access paths in a defined landing area.

The customer does not need an existing metadata framework. The repo provides the metadata framework by normalizing raw exports into a common asset, dependency, risk and blueprint model.

## Product operating model

1. Deploy the accelerator bundle to a customer Databricks workspace.
2. Create a governed metadata landing area in Unity Catalog.
3. Ask the customer to export legacy metadata into that landing area.
4. Run the accelerator jobs.
5. Review the generated summary, priority matrix, dependency graph, risk register, target blueprint and data quality plan.
6. Publish graph outputs to Neo4j for visual impact analysis.
7. Index artifacts with Databricks Vector Search for semantic discovery.
8. Use MLflow when generated recommendations, RAG or assistant workflows are introduced.
9. Choose the migration execution pattern per source: managed Delta ingestion, external table registration, Lakehouse Federation, or source-specific connectors.

The first delivery focuses on steps 1 to 5. Steps 6 to 9 are activated after the first Databricks outputs are trusted and credentials are approved.

Before positioning the accelerator, review `docs/00_PRODUCT_POSITIONING.md`. It defines where this product fits, when existing tools are better and how to decide between federation, ingestion, external tables and volumes.

For the first real Databricks execution, follow `docs/02_FIRST_RUN_RUNBOOK.md`. For customer discovery, use `contracts/customer_intake_checklist.md`.

For Neo4j, Vector Search, RAG, MLflow and Model Serving planning, use `docs/05_ADVANCED_CAPABILITIES.md`. These are part of the full solution and are activated after the first Databricks run is trusted.

## Metadata landing contract

Recommended landing location:

```text
/Volumes/<catalog>/landing/legacy_metadata/
```

Recommended folders:

```text
/Volumes/<catalog>/landing/legacy_metadata/adf/
/Volumes/<catalog>/landing/legacy_metadata/synapse/inventory/
/Volumes/<catalog>/landing/legacy_metadata/synapse/notebooks/
/Volumes/<catalog>/landing/legacy_metadata/synapse/sql/
/Volumes/<catalog>/landing/legacy_metadata/sqlserver/inventory/
/Volumes/<catalog>/landing/legacy_metadata/docs/
```

The baseline CSV shape is defined in:

```text
contracts/legacy_metadata_inventory.csv
```

An example landing manifest is defined in:

```text
contracts/landing_manifest.example.json
```

The current parser supports these file families:

- ADF pipeline exports as `.json`.
- ADF dataset, linked service and trigger exports as `.json`.
- Synapse or SQL Server inventory extracts as `.csv`.
- Synapse notebooks as `.ipynb`.
- SQL scripts, views, procedures and external table DDL as `.sql`.

Source-specific extractors can become richer over time, but the product boundary remains the same: the accelerator consumes metadata exports from a landing area and writes Delta outputs.

## How to read first-run results

The first run is consumed directly in Databricks. Neo4j and Vector Search enrich the same outputs after credentials and security setup are ready.

Use these Delta tables first:

- `gold.assessment_summary`: one-row executive view of the run.
- `gold.asset_priority_matrix`: prioritized review backlog for migration analysts.
- `gold.graph_edges`: readable dependency relationships for impact analysis.
- `gold.risk_register`: risk scores, factors and recommended actions.
- `gold.target_databricks_blueprint`: proposed Databricks target patterns.
- `gold.data_quality_plan`: validation checks to execute during migration.

Interpretation flow:

1. Start with `gold.assessment_summary`.
2. Open `gold.asset_priority_matrix` and filter `review_priority = 'p1'`.
3. For a priority asset, inspect related rows in `gold.graph_edges`.
4. Confirm risk detail in `gold.risk_register`.
5. Confirm target pattern in `gold.target_databricks_blueprint`.
6. Use `gold.data_quality_plan` as the validation backlog.

Neo4j makes graph exploration visual. Vector Search makes discovery semantic. Both build on these Delta outputs.

## What the customer provides

For ADF:

- Factory pipeline JSON exports.
- Dataset and linked service exports when available.
- Trigger exports when orchestration timing matters.

For Synapse:

- Dedicated pool object inventory.
- Serverless database inventory.
- External table DDL or metadata extract.
- Notebook exports.
- SQL scripts, views, stored procedures and dependency extracts.

For SQL Server:

- Object inventory from system catalogs.
- Row counts and table sizes.
- Module definitions for views, procedures and functions.
- Dependency extracts from `sys.sql_expression_dependencies` when available.
- Optional sample profiling outputs for data quality planning.

For the data lake:

- Storage account/container paths.
- Existing folder layout.
- File formats and partition conventions.
- External table locations already used by Synapse serverless.
- Security model and ownership boundaries.

## SQL Server in this repository

The SQL Server Docker fixture is not the customer architecture.

It exists so developers can:

- Simulate a legacy SQL Server estate locally.
- Test metadata extraction repeatably.
- Generate a sample inventory without needing customer infrastructure.

In a real implementation, the customer would run approved metadata extraction SQL against their SQL Server instances, or grant read-only metadata access to an implementation service account. The accelerator should receive the output CSV or JSON during initial discovery.

The starter SQL Server extraction query is:

```text
samples/sqlserver/extract/metadata_inventory.sql
```

## Real SQL Server implementation

For a real SQL Server estate, use one of three patterns:

- Export-only discovery: the customer runs approved read-only metadata queries and drops CSV/JSON outputs into the landing folder.
- Lakehouse Federation: Databricks queries SQL Server live for discovery, validation or reconciliation when network and governance allow it.
- Connector-based ingestion: Databricks ingests selected source tables when the migration execution plan requires managed Delta outputs.

Use export-only discovery first unless the customer already has approved network connectivity and secret handling. It is the lowest-friction and lowest-risk onboarding path.

## Data lake and Synapse external tables

Synapse serverless external tables usually point to files already stored in a lake. The accelerator should capture both sides:

- The logical table object: database, schema, external table name, columns and dependencies.
- The physical storage path: container, folder, file format and partition pattern.

In this repo, this is represented by:

- `samples/legacy_metadata/synapse_tables.csv`
- `samples/legacy_metadata/synapse_serverless_external_tables.sql`

In a customer implementation, the same information should come from Synapse metadata exports and cloud storage inventory.

## Target pattern decision matrix

Use managed Delta tables when:

- Databricks becomes the system of record for analytical tables.
- Performance, governance, optimization and simplified operations matter.
- The customer accepts copying or transforming source data into the lakehouse.

Use Unity Catalog external tables when:

- Data already exists in cloud object storage.
- Another platform still owns the physical file lifecycle.
- The migration needs to register large existing datasets without immediate copy.

Use Unity Catalog volumes when:

- The asset is non-tabular, semi-structured, raw documentation, notebooks, scripts or exported metadata.
- Users or jobs need governed path-based access through `/Volumes`.

Use Lakehouse Federation when:

- The customer needs live query access to SQL Server, Synapse, Snowflake or another supported source.
- The use case is discovery, validation, reconciliation or ad hoc reporting.
- Moving data immediately is not desirable.

Use ingestion connectors or Lakeflow-style ingestion when:

- Higher-volume, repeatable, lower-latency ingestion is required.
- Databricks should own curated Delta outputs.
- The workload is part of the real migration execution, not just assessment.

## Recommended product stance

The accelerator should be plug-and-play for assessment:

- Customer exports metadata to the landing contract.
- Implementation team configures `.env` or bundle variables.
- Databricks bundle deploys jobs.
- Jobs generate control, silver and gold Delta outputs.

The accelerator should be configurable, not magical, for execution:

- Each customer source has different access, security, volume and latency constraints.
- The generated blueprint should recommend target patterns.
- Human review confirms which patterns become implementation work.

This keeps the accelerator usable as a product while avoiding risky assumptions about production data movement.

## Minimal customer onboarding checklist

Before the first Databricks run:

- Full Databricks workspace, not Free Edition.
- Unity Catalog enabled.
- Target catalog name agreed.
- Metadata landing volume or external volume agreed.
- Databricks CLI profile configured.
- Sample metadata uploaded to the landing path.

Before real source connectivity:

- Source system owners identified.
- Read-only metadata access approved.
- Secrets strategy agreed.
- Network path from Databricks to source approved, if direct connectivity is required.
- Decision made per source: export-only discovery, federation, connector-based ingestion or custom extraction.
