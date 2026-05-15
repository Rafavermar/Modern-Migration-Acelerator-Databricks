# Phase 2: Neo4j Graph Extension

Neo4j is planned after the MVP Delta dependency graph is working in Databricks.

## MVP boundary

The MVP stores graph edges in Delta:

- `silver.assets`
- `silver.dependencies`

Do not make Neo4j required for the first Databricks deployment. The Databricks run should succeed without a Neo4j account, driver, secrets or network configuration.

## When to provide Neo4j details

Provide Neo4j connection details after:

1. The Full Trial Databricks workspace is created.
2. The bundle validates against that workspace.
3. The accelerator job has produced the Delta control, silver and gold tables.

At that point we can add a controlled exporter from Delta graph tables to Neo4j.

## Details needed later

- Neo4j URI.
- Database name.
- Username or authentication method.
- Secret storage location for credentials.
- TLS requirement.
- Network access path from Databricks to Neo4j.
- Export mode: read-only graph publishing or bidirectional sync.

## Future graph model

Initial node labels:

- `Asset`
- `Pipeline`
- `Notebook`
- `Table`
- `ExternalTable`
- `ServerlessDatabase`
- `Procedure`

Initial relationships:

- `DEPENDS_ON`
- `READS`
- `WRITES`
- `ORCHESTRATES`
- `REFERENCES`

The Delta tables remain the source of truth. Neo4j is a graph exploration and impact analysis extension.
