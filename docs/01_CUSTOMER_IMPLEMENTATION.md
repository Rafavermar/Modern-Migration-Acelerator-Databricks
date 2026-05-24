# Customer Implementation Guide

This accelerator should be treated as a deployable product, not as a folder of examples.

The customer does not copy this repository into every legacy system. The implementation team deploys the repository once, then the customer provides exports and access paths in a defined landing area.

The customer does not need an existing metadata framework. The repo provides the metadata framework by normalizing raw exports into a common asset, dependency, risk and blueprint model.

## What the customer gets

The first customer outcome is a Databricks-native migration assessment, not a completed production migration.

The accelerator produces:

- what legacy assets exist;
- how they depend on each other;
- which assets are high risk or first-wave candidates;
- which Databricks target pattern is recommended;
- which validation checks should be planned;
- where architects can inspect the graph, search evidence and trace generated answers.

The customer uses those outputs to execute migration work through approved Databricks engineering patterns.

## Product operating model

1. Deploy the accelerator bundle to a customer Databricks workspace with serverless jobs.
2. Create a governed metadata landing area in Unity Catalog.
3. Ask the customer to export legacy metadata into that landing area.
4. Run the accelerator jobs.
5. Review the generated summary, priority matrix, dependency graph, risk register, target blueprint and data quality plan.
6. Publish graph outputs to Neo4j for visual impact analysis.
7. Index artifacts with Databricks Vector Search for semantic discovery.
8. Use the RAG/search utility to ask migration questions over the indexed corpus.
9. Use MLflow when generated recommendations or assistant workflows are introduced.
10. Choose the migration execution pattern per source: managed Delta ingestion, external table registration, Lakehouse Federation, or source-specific connectors.

The first Databricks run proves the assessment backbone. Graph, search and RAG/search run from the same outputs once credentials and security approval are in place.

Before positioning the accelerator, review `docs/00_PRODUCT_POSITIONING.md`. It defines where this product fits, when existing tools are better and how to decide between federation, ingestion, external tables and volumes.

For the first real Databricks execution, follow `docs/02_FIRST_RUN_RUNBOOK.md`. For customer discovery, use `contracts/customer_intake_checklist.md`.

For Neo4j, Vector Search, RAG, MLflow and Model Serving planning, use `docs/05_ADVANCED_CAPABILITIES.md`. These are part of the full solution and are activated after the first Databricks run is trusted.

## Customer connection map

| Input | Where it is configured | What changes for a customer |
| --- | --- | --- |
| Databricks workspace | `.env`, `DATABRICKS_PROFILE`, `DATABRICKS_CATALOG` | Use the customer workspace profile and target catalog. |
| Metadata root | `LEGACY_METADATA_SOURCE_ROOT` | Point to the customer Unity Catalog volume or external volume. |
| ADF/Synapse/notebooks/SQL | Metadata landing folders | Drop exported files into the expected folders. |
| SQL Server | Export CSV/JSON or approved direct access | Start with export-only discovery unless network and secrets are already approved. |
| Neo4j | `.env` locally, secrets for enterprise | Publish the graph after the Databricks Delta outputs are trusted. |
| Vector Search, RAG and MLflow | `.env`, Databricks resources and MLflow experiment | Use after `gold.semantic_legacy_documents` exists and indexing is approved. |

## Metadata landing contract

Recommended landing location:

```text
/Volumes/<catalog>/landing/legacy_metadata/
```

For demo-only runs, the scripts use:

```text
/Volumes/<catalog>/landing/legacy_metadata/demo
```

Do not use `/Workspace/.../.bundle/.../files` as a metadata landing path. Workspace Files are for bundle code; metadata input belongs in a Unity Catalog volume.

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

## Demo vs customer mode

Demo mode:

- Leave `LEGACY_METADATA_SOURCE_ROOT` empty.
- Run `bash scripts/run_accelerator_dev.sh`.
- The script uploads `samples/legacy_metadata` to `/Volumes/<catalog>/landing/legacy_metadata/demo`.

Customer mode:

- Export customer artifacts to `/Volumes/<catalog>/landing/legacy_metadata/`.
- Set `LEGACY_METADATA_SOURCE_ROOT` to that volume path.
- Validate, deploy and run the bundle again.

Only the source path changes. The Databricks jobs, parsers and output tables stay the same.

The scripts also upload runtime Python entrypoints to `/Volumes/<catalog>/landing/legacy_metadata/runtime` so serverless jobs do not depend on reading task code from Workspace Files.

## How to read first-run results

The first run is consumed directly in Databricks. Neo4j and Vector Search enrich the same outputs after credentials and security setup are ready.

Use these Delta tables first:

- `gold.assessment_summary`: one-row executive view of the run.
- `gold.asset_priority_matrix`: prioritized review backlog for migration analysts.
- `gold.graph_edges`: readable dependency relationships for impact analysis.
- `gold.risk_register`: risk scores, factors and recommended actions.
- `gold.target_databricks_blueprint`: proposed Databricks target patterns.
- `gold.data_quality_plan`: validation checks to execute during migration.
- `gold.semantic_legacy_documents`: chunked artifacts and generated outputs for Vector Search.

Interpretation flow:

1. Start with `gold.assessment_summary`.
2. Open `gold.asset_priority_matrix` and filter `review_priority = 'p1'`.
3. For a priority asset, inspect related rows in `gold.graph_edges`.
4. Confirm risk detail in `gold.risk_register`.
5. Confirm target pattern in `gold.target_databricks_blueprint`.
6. Use `gold.data_quality_plan` as the validation backlog.
7. Use `gold.semantic_legacy_documents` as the source table for semantic indexing.

Neo4j makes graph exploration visual. Vector Search makes discovery semantic. Both build on these Delta outputs.

## How migration execution starts

After the assessment is reviewed, migration execution starts from the gold outputs:

| Question | Output to use | Execution decision |
| --- | --- | --- |
| What moves first? | `gold.asset_priority_matrix` | Select wave 1 assets and review backlog. |
| What could break? | `gold.graph_edges`, Neo4j | Check upstream/downstream dependencies before implementation. |
| What should the target be? | `gold.target_databricks_blueprint` | Choose Delta table, external table, volume, federation or connector pattern. |
| What must be validated? | `gold.data_quality_plan` | Define pre/post migration checks and ownership. |
| What is risky? | `gold.risk_register` | Decide mitigation, sequencing and manual review. |

Then the delivery team implements the chosen pattern:

- managed Delta ingestion for Databricks-owned analytical tables;
- external tables or volumes for data already in governed cloud storage;
- Lakehouse Federation for live access, validation or phased coexistence;
- Lakeflow or connector-based ingestion for repeatable source-to-Delta movement;
- Databricks jobs, notebooks or workflows for transformed logic.

The accelerator can be re-run after new exports or implementation changes to refresh priorities and validate that the plan still matches the estate.

To publish the graph after the first trusted run:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\publish_neo4j_graph.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\verify_neo4j_graph.ps1
```

To activate semantic search after `gold.semantic_legacy_documents` exists:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\create_vector_search_dev.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\query_vector_search_dev.ps1 -Query "Which assets should be migrated first?"
powershell -ExecutionPolicy Bypass -File .\scripts\rag_search_dev.ps1 -Question "Which assets should be migrated first?"
```

The dev index uses `chunk_id` as primary key, `chunk_text` as the embedding source, `databricks-qwen3-embedding-0-6b` as the embedding endpoint and `TRIGGERED` sync mode.

For managed embeddings, Databricks uses the same configured embedding endpoint for indexed text and `query_text`. If a customer later provides their own vectors, they must keep the same model, dimensions and preprocessing for both indexing and querying.

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

For extractor improvements:

- Representative redacted artifacts for each source pattern.
- Expected lineage/dependency outcomes for those artifacts.
- Known dynamic patterns that static parsing might miss.
- Any existing catalog, lineage or dependency exports.

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

The local Docker fixture is optional. A customer does not need Docker if they can provide SQL Server metadata exports.

### Pattern 1: Export-only discovery

Use when the customer wants the fastest and least invasive assessment.

Technical flow:

1. DBA reviews `samples/sqlserver/extract/metadata_inventory.sql`.
2. DBA runs the query with read-only catalog permissions.
3. Output is saved as CSV using the contract in `contracts/legacy_metadata_inventory.csv`.
4. File is uploaded to:

```text
/Volumes/<catalog>/landing/legacy_metadata/sqlserver/inventory/
```

5. Set `LEGACY_METADATA_SOURCE_ROOT=/Volumes/<catalog>/landing/legacy_metadata`.
6. Run the accelerator normally.

This pattern does not require network connectivity from Databricks to SQL Server.

### Pattern 2: Lakehouse Federation

Use when Databricks must query SQL Server live for validation, reconciliation or read-only discovery.

Prerequisites:

- Unity Catalog enabled.
- User has `CREATE CONNECTION` privilege or metastore admin support.
- Network route from Databricks to SQL Server is approved.
- Authentication mode is approved: basic auth, OAuth or OAuth machine-to-machine.
- Credentials are stored in Databricks secrets or a customer-approved secret manager.

UI path:

1. Open `Catalog`.
2. Click the add icon at the top of the Catalog pane.
3. Select `Create a connection`.
4. Choose connection type `SQL Server`.
5. Create a foreign catalog that mirrors the SQL Server database.

SQL shape:

```sql
CREATE CONNECTION mma_sqlserver_connection
TYPE SQLSERVER
OPTIONS (
  host '<sql-server-host>',
  port '1433',
  user secret('<scope>', '<user-key>'),
  password secret('<scope>', '<password-key>')
);

CREATE FOREIGN CATALOG legacy_sqlserver
USING CONNECTION mma_sqlserver_connection
OPTIONS (database '<database-name>');
```

After the foreign catalog exists, the accelerator can use metadata exported from that catalog, or a customer-specific extractor can query `legacy_sqlserver.<schema>.<table>` for validation.

Do not use federation as the first choice if the only need is static migration assessment and the customer can provide exports.

### Pattern 3: Connector-based ingestion

Use when the migration plan requires Databricks-owned Delta copies of source tables.

Technical flow:

1. Use the accelerator outputs to decide which SQL Server tables need ingestion.
2. Configure customer-approved ingestion, such as Lakeflow Connect or another approved connector pattern.
3. Store raw or bronze ingested data in managed Delta tables.
4. Keep the accelerator metadata landing separate from production data ingestion.

This is migration execution, not just assessment. It should follow customer data movement, retention and cost policies.

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
- Databricks bundle deploys serverless jobs.
- Jobs generate control, silver and gold Delta outputs.
- Self-contained serverless Python tasks are the default; classic job clusters are a customer-specific override.

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

## Official References

- Databricks SQL Server Lakehouse Federation: https://docs.databricks.com/aws/en/query-federation/sql-server
- Databricks connections: https://docs.databricks.com/aws/en/query-federation/connections
- `CREATE CONNECTION`: https://docs.databricks.com/aws/en/sql/language-manual/sql-ref-syntax-ddl-create-connection
