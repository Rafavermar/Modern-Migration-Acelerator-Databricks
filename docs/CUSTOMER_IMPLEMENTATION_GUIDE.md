# Customer Implementation Guide

This accelerator should be treated as a deployable product, not as a folder of examples.

The customer does not copy this repository into every legacy system. The implementation team deploys the repository once, then the customer provides exports and access paths in a defined landing area.

## Product operating model

1. Deploy the accelerator bundle to a customer Databricks workspace.
2. Create a governed metadata landing area in Unity Catalog.
3. Ask the customer to export legacy metadata into that landing area.
4. Run the accelerator jobs.
5. Review the generated risk register, dependency graph, target blueprint and data quality plan.
6. Choose the migration execution pattern per source: managed Delta ingestion, external table registration, Lakehouse Federation, or source-specific connectors.

The MVP focuses on steps 1 to 5. Step 6 is where implementation choices become customer-specific.

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

The current MVP parser supports these file families:

- ADF pipeline exports as `.json`.
- ADF dataset, linked service and trigger exports as `.json`.
- Synapse or SQL Server inventory extracts as `.csv`.
- Synapse notebooks as `.ipynb`.
- SQL scripts, views, procedures and external table DDL as `.sql`.

Future phases can add richer source-specific extractors, but the product boundary remains the same: the accelerator consumes metadata exports from a landing area and writes Delta outputs.

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

In a real implementation, the customer would run approved metadata extraction SQL against their SQL Server instances, or grant read-only metadata access to an implementation service account. The accelerator should receive the output CSV or JSON, not direct production database credentials during MVP discovery.

The starter SQL Server extraction query is:

```text
samples/sqlserver/extract/metadata_inventory.sql
```

Direct SQL Server connectivity can be added later for automated discovery, but it should be optional and controlled because network access, credentials, approvals and data handling policies vary by customer.

## Data lake and Synapse external tables

Synapse serverless external tables usually point to files already stored in a lake. The accelerator should capture both sides:

- The logical table object: database, schema, external table name, columns and dependencies.
- The physical storage path: container, folder, file format and partition pattern.

In the MVP, this is represented by:

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

This keeps the MVP usable as a product while avoiding risky assumptions about production data movement.

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
