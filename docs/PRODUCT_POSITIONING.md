# Product Positioning

This accelerator is a migration assessment product for Databricks modernization.

It is not an enterprise catalog, data movement engine, database migration service or automatic code converter.

## Core Scope

Use it to:

- Ingest legacy metadata exports.
- Normalize assets and dependencies.
- Build a graph-ready Delta model.
- Generate risk, target blueprint and data quality planning outputs.
- Help decide the migration execution pattern per source.

Do not use it as the system of record for enterprise governance, security classification or production lineage.

## Why It Still Makes Sense

Existing tools are strong, but they do not fully answer the same question:

> What do we have, how risky is it, how does it depend on other assets, and what should its Databricks target pattern be?

This accelerator is useful because it packages that assessment into Databricks-native Delta outputs and customer-reviewable recommendations.

## Existing Tools That Can Be Stoppers

Stop or reposition the accelerator if the customer already has a tool that fully covers the same outcome.

### Microsoft Purview

Purview can scan data sources, extract metadata, apply classification and ingest lineage from ADF and Synapse. If the customer already has a complete Purview implementation with curated ownership, classification, lineage and migration-ready exports, this accelerator should not duplicate scanning.

Use this accelerator only as a Databricks migration planning layer over Purview exports.

### Unity Catalog Lineage

Unity Catalog captures runtime lineage for Databricks queries, jobs, notebooks and tables. If the workload is already running in Databricks and the need is operational lineage, use Unity Catalog lineage directly.

Use this accelerator for pre-migration legacy analysis, not as a replacement for runtime Databricks lineage.

### Lakehouse Federation

Lakehouse Federation supports live query access to external systems such as SQL Server and Azure Synapse. If the only requirement is live access without migration assessment, use federation directly.

Use this accelerator when the customer needs impact analysis, risk scoring and target pattern recommendations before deciding whether to federate, ingest or register external tables.

### Azure Database Migration Service and SSMA

Azure migration tooling is better suited for database engine migration paths such as SQL Server to Azure SQL. If the target is Azure SQL, not Databricks, this accelerator is the wrong primary tool.

Use this accelerator when the target is a Databricks lakehouse and the migration includes pipelines, notebooks, lake files, SQL scripts and orchestration.

### Enterprise Catalogs and Lineage Platforms

If the customer already owns a mature catalog such as Purview, Collibra, Informatica or another governed metadata platform, do not position this accelerator as a replacement.

Use it as a focused migration workbench that consumes or exports metadata.

## Strengths

- Low-friction assessment using metadata exports.
- No production credentials required for the first MVP run.
- Databricks-native outputs in Delta.
- Simple graph model: assets and dependencies.
- Explicit target blueprint and data quality planning.
- Works before Databricks production connectivity is approved.

## Weaknesses

- Not a full scanner for every source.
- Not a replacement for Purview or Unity Catalog governance.
- Not an automated code conversion engine.
- Not a high-volume ingestion framework.
- Not a production scheduler beyond the Databricks jobs it defines.
- Accuracy depends on metadata export completeness.

## Use It When

- The customer is starting a Databricks modernization assessment.
- Legacy ADF, Synapse, SQL Server, SQL scripts and notebooks must be inventoried together.
- The team needs quick risk and dependency visibility.
- The migration target pattern is not yet agreed.
- Data movement approvals are not ready, but metadata exports are possible.

## Do Not Use It When

- The customer only needs live queries against source systems.
- The target platform is not Databricks.
- The customer expects automatic conversion of all pipelines and notebooks.
- Metadata exports cannot be provided and direct source access is also blocked.
- Enterprise governance, classification or regulatory cataloging is the primary deliverable.

## Federation Decision

Choose federation when:

- Live source access is needed for assessment, reconciliation or short-term reporting.
- Data movement should be minimized.
- Source load is acceptable.
- Query latency and pushdown limitations are acceptable.
- The source is expected to remain active during a phased migration.

Avoid federation when:

- Workloads are high-volume or latency-sensitive.
- The source cannot absorb additional query load.
- Transformation logic should become Databricks-owned.
- Historical replay, CDC, optimization or Delta performance is required.
- Network, credential or governance policies block live connectivity.

## Preferred Migration Pattern

For most modernization programs, use this order:

1. Export metadata and run this accelerator.
2. Use federation only where live access is useful.
3. Ingest priority datasets into Delta when performance, ownership or repeatability matter.
4. Register external tables or volumes where data already lives in governed cloud storage.
5. Use Unity Catalog lineage for workloads after they run in Databricks.
6. Integrate with Purview or another catalog if enterprise governance requires it.

## Bottom Line

The accelerator is strongest as a plug-and-play Databricks migration assessment layer.

It should complement specialized tools, not compete with them. Its value is speed, focus and Databricks-oriented migration decisions.

## Reference Points

- Databricks Lakehouse Federation: https://docs.databricks.com/en/query-federation/
- Databricks Unity Catalog lineage: https://docs.databricks.com/en/data-governance/unity-catalog/data-lineage.html
- Microsoft Purview Data Map scans and ingestion: https://learn.microsoft.com/en-us/purview/data-map-scan-ingestion
- Azure Database Migration Service: https://learn.microsoft.com/en-us/azure/dms/
