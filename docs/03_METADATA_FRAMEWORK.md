# Metadata Framework

The metadata framework is intentionally small. It defines enough structure to make the accelerator useful and extensible without introducing an enterprise metadata platform.

## Core entities

The accelerator normalizes all discovered artifacts into two graph-ready tables:

- `silver.assets`
- `silver.dependencies`

Assets describe things. Dependencies describe relationships between things.

Human-facing gold outputs are derived from those tables:

- `gold.assessment_summary`
- `gold.asset_priority_matrix`
- `gold.graph_edges`
- `gold.risk_register`
- `gold.target_databricks_blueprint`
- `gold.data_quality_plan`

The initial taxonomy is stored in:

```text
contracts/metadata_taxonomy.json
```

## Asset principles

Each asset should have:

- Stable deterministic `asset_id`.
- `source_system`.
- Normalized `asset_type`.
- Human-readable `asset_name`.
- Original `raw_path`.
- Sanitized `metadata_json`.

Secrets and connection strings must not be preserved in `metadata_json`.

## Relationship principles

Relationships should be directional and evidence-backed:

- `from_asset_id`
- `to_asset_id`
- `dependency_type`
- `evidence`
- `confidence`

This is enough for impact analysis, risk scoring and a future Neo4j export.

## Current coverage

ADF:

- Pipelines.
- Activities.
- Dataset references from activity inputs and outputs.
- Dataset definitions.
- Linked services.
- Triggers.
- Table and storage path references derived from datasets.

Synapse:

- Dedicated SQL tables and views.
- Serverless databases.
- External tables and lake paths.
- Notebook SQL references.
- SQL scripts and DDL references.
- Optional Databricks Lakebridge Analyzer `.xlsx` reports for SQL program complexity and object cross-references.

SQL Server:

- Local Docker fixture for developer tests.
- Starter metadata extraction query for real customer environments.

## Scoring and priority rules

Risk and priority are calculated by the accelerator. The customer does not need to manually tag every artifact.

Current rule engine:

- Code: `src/modern_migration_accelerator/pipelines/run_accelerator.py`.
- Risk table: `build_risk_register()`.
- Priority table: `build_asset_priority_matrix()`.
- Target pattern table: `build_blueprint()`.
- Data quality backlog: `build_data_quality_plan()`.

Risk starts from a baseline score and increases when metadata shows:

- high `criticality`;
- many dependencies;
- large `row_count`;
- orchestration or code migration;
- connection, dataset, external table or security mapping work.

Review priority is derived from risk and dependencies:

- `p1`: `risk_score >= 70` or at least 5 dependencies;
- `p2`: `risk_score >= 40` or at least 2 dependencies;
- `p3`: standard review path.

Customers can improve the quality of the scoring by providing richer exports. Useful input fields include `criticality`, `row_count`, `depends_on`, owner, object type, storage location and module definitions. The rules are deterministic and intentionally simple; customer-specific weights can be added later without changing the output model.

## Extractor boundaries

Extractors are the source-specific adapters that convert raw exports into the common metadata model:

- ADF JSON to assets and dependencies.
- Synapse or SQL Server CSV inventory to assets.
- SQL scripts and DDL to object references.
- Notebooks to referenced tables, views and SQL snippets.
- Lakebridge Analyzer reports to SQL program assets and read/write object dependencies.
- Generated Delta outputs to semantic chunks for Vector Search.

They live mainly in:

- `src/modern_migration_accelerator/pipelines/run_accelerator.py`
- `src/modern_migration_accelerator/parsers/sql.py`
- `src/modern_migration_accelerator/pipelines/run_semantic_index_prep.py`
- `samples/sqlserver/extract/metadata_inventory.sql`

Future extractor improvements do not mean changing the product architecture. They mean teaching the accelerator to understand more customer-specific artifact shapes while still writing the same `silver` and `gold` outputs.

## What is needed to improve extractors

Ask the customer for representative metadata samples, not production data dumps:

- 3-5 redacted examples per source pattern: ADF pipeline, dataset, linked service, trigger, Synapse notebook, SQL script, SQL Server procedure, external table.
- The expected dependency interpretation for those examples.
- Known edge cases: parameterized paths, dynamic SQL, stored procedures, custom orchestration frameworks, naming conventions.
- Existing catalog or lineage exports when available, such as Purview, Synapse inventory or SQL dependency extracts.
- A small validation set: assets and dependencies the customer expects the accelerator to find.

Stable formats with examples are usually low to moderate effort. Runtime-only dependencies, dynamic strings, missing exports or custom frameworks require more discovery and may need customer-specific extractor rules.

## Deliberate non-goals

The accelerator does not try to replace enterprise catalogs, scanners or lineage platforms. It creates a lightweight, Databricks-native metadata layer that can be enriched by source-specific extractors, exported to Neo4j and indexed for semantic search.
