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

SQL Server:

- Local Docker fixture for developer tests.
- Starter metadata extraction query for real customer environments.

## Deliberate non-goals

The accelerator does not try to replace enterprise catalogs, scanners or lineage platforms. It creates a lightweight, Databricks-native metadata layer that can be enriched by source-specific extractors, exported to Neo4j and indexed for semantic search.
