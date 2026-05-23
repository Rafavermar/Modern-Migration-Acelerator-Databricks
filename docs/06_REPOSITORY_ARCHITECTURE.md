# Repository Architecture

This document explains the product architecture, the Databricks resources that are created and where each repo piece fits.

## Architecture Layers

```mermaid
flowchart LR
    A[Legacy estate\nADF, Synapse, SQL Server, notebooks, SQL, docs] --> B[Metadata landing\nUnity Catalog Volume]
    B --> C[Databricks Asset Bundle\njobs + runtime scripts]
    C --> D[Assessment job\nparse, normalize, score, blueprint]
    D --> E[Delta outputs\nbronze, silver, gold, control]
    E --> F[Databricks review\nsummary, priority, risks, blueprint, DQ]
    E --> G[Neo4j AuraDB\nimpact graph]
    E --> H[Semantic corpus\nsanitized chunks]
    H --> I[Vector Search\nDelta Sync hybrid index]
    I --> J[RAG / assistant workflows\nwith MLflow tracing]
```

### Global Platform Layer

| Platform | Role |
| --- | --- |
| Databricks | Runs the bundle, serverless jobs, Delta outputs, Unity Catalog governance, Vector Search and future MLflow/RAG workflows. |
| Unity Catalog | Governs the catalog, schemas, tables, volumes, vector index and optional federated connections. |
| Neo4j AuraDB | Graph exploration for migration impact analysis. Delta remains the assessment source of truth. |
| SQL Server | Local Docker fixture for demo; real customer source can use export-only discovery, Lakehouse Federation or connector-based ingestion. |

### Databricks Assessment Layer

| Component | Function |
| --- | --- |
| Metadata landing volume | Stores raw exported artifacts and runtime Python scripts in governed storage. |
| Accelerator job | Parses raw artifacts, normalizes assets/dependencies, scores risk and writes Delta outputs. |
| Target demo job | Consumes the generated blueprint and creates a simple target migration plan table. |
| Semantic prep job | Creates sanitized chunks from legacy artifacts and generated outputs for Vector Search. |
| Vector Search index | Provides semantic and hybrid retrieval over the migration estate. |

### Advanced AI Layer

| Component | Function |
| --- | --- |
| Embedding model endpoint | Converts `chunk_text` into vectors. Dev uses `databricks-qwen3-embedding-0-6b`. |
| Vector Search endpoint | Serves the vector index for retrieval queries. Dev uses `mma-vector-search-dev`. |
| RAG workflow | Future layer that retrieves relevant chunks and asks an LLM to answer migration questions. |
| MLflow | Future tracing/evaluation layer for prompts, retrieved context, generated responses and human review. |
| Model Serving / AI Gateway | Future interactive serving layer if the accelerator exposes an assistant endpoint. |

## Databricks UI Map

Use this map when validating the workspace manually.

| What to inspect | Where in Databricks UI | Expected dev object |
| --- | --- | --- |
| Bundle jobs | `Jobs & Pipelines` | `modern_migration_accelerator_databricks-dev-accelerator`, `...-target-demo`, `...-semantic-index-prep` |
| Delta outputs | `Catalog` > `migration_accelerator_dev` | Schemas `bronze`, `silver`, `gold`, `control`, `demo` |
| Metadata volume | `Catalog` > `migration_accelerator_dev` > `landing` | Volume `legacy_metadata` |
| Source table for semantic search | `Catalog` > `migration_accelerator_dev` > `gold` | Table `semantic_legacy_documents` |
| Vector Search index | `Catalog` search or `Catalog` > `migration_accelerator_dev` > `gold` | Managed vector index `semantic_legacy_documents_vs` |
| Vector index sync | Vector index page > `Overview` > `Data Ingest` | `Sync now` for triggered sync |
| Vector Search endpoint | CLI/API, and Vector Search index details | Endpoint `mma-vector-search-dev` |
| Embedding model endpoint | AI Gateway / Foundation Model endpoints, depending workspace UI and filters | `databricks-qwen3-embedding-0-6b` |

Do not expect `mma-vector-search-dev` to appear under `AI/ML > Serving` as a normal user-created serving endpoint. Vector Search endpoints are managed separately from Model Serving endpoints. The index is visible and governed in Unity Catalog. The endpoint is easiest to verify with:

```bash
databricks --profile <profile> vector-search-endpoints get-endpoint mma-vector-search-dev
databricks --profile <profile> vector-search-indexes get-index migration_accelerator_dev.gold.semantic_legacy_documents_vs
```

If you are using PowerShell or Git Bash scripts from this repo, they load `DATABRICKS_PROFILE` from `.env`.

## Databricks Resources

Default dev deployment creates or uses:

| Resource | Name or path | Purpose |
| --- | --- | --- |
| Bundle target | `dev` | Local development deployment target. |
| Catalog | `migration_accelerator_dev` | Default Unity Catalog catalog for dev outputs. |
| Volume | `/Volumes/migration_accelerator_dev/landing/legacy_metadata/` | Governed metadata landing and runtime script location. |
| Runtime scripts | `/Volumes/<catalog>/landing/legacy_metadata/runtime/` | Serverless-safe Python task entrypoints. |
| Demo metadata | `/Volumes/<catalog>/landing/legacy_metadata/demo/` | Uploaded sample artifacts plus optional local SQL Server export. |
| Job | `modern_migration_accelerator_databricks-dev-accelerator` | Parse metadata and write assessment outputs. |
| Job | `modern_migration_accelerator_databricks-dev-target-demo` | Build a demo target migration plan from the blueprint. |
| Job | `modern_migration_accelerator_databricks-dev-semantic-index-prep` | Build Vector Search-ready semantic chunks. |
| Vector Search endpoint | `mma-vector-search-dev` | Serves the semantic search index. |
| Vector Search index | `migration_accelerator_dev.gold.semantic_legacy_documents_vs` | Delta Sync hybrid index over semantic chunks. |
| Embedding endpoint | `databricks-qwen3-embedding-0-6b` | Databricks-hosted embedding model used by the index. |

Current dev validation:

| Check | Result |
| --- | --- |
| Semantic chunks | `309` rows indexed. |
| Index readiness | `ready=true`. |
| Index type | `DELTA_SYNC`. |
| Index subtype | `HYBRID`. |
| Sync mode | `TRIGGERED`. |
| Primary key | `chunk_id`. |
| Text column | `chunk_text`. |

Databricks also creates internal service resources for Vector Search, such as a Delta Sync pipeline ID. Those IDs are workspace-generated and should not be hardcoded in the repo.

## Bundle Structure

| Path | Purpose |
| --- | --- |
| `databricks.yml` | Bundle name, target and variables such as catalog and metadata source root. |
| `resources/jobs.yml` | Databricks jobs: assessment, target demo and semantic index prep. |
| `samples/legacy_metadata/` | Demo estate used for the first run. |
| `samples/sqlserver/` | Local SQL Server fixture, seed data and metadata extraction query. |
| `contracts/` | Customer intake checklist, inventory CSV contract and metadata taxonomy. |
| `scripts/validate_bundle.sh` | Validate bundle configuration before deploy. |
| `scripts/deploy_dev.sh` | Upload runtime scripts, prepare the volume and deploy jobs. |
| `scripts/run_accelerator_dev.sh` | Run the assessment job. |
| `scripts/run_target_demo_dev.sh` | Run the blueprint consumer demo job. |
| `scripts/run_semantic_index_prep_dev.sh` | Run the semantic corpus preparation job. |
| `scripts/create_vector_search_dev.*` | Create/sync the dev Vector Search endpoint and index. |
| `scripts/query_vector_search_dev.*` | Query the Vector Search index with a natural-language question. |
| `scripts/publish_neo4j_graph.*` | Publish the normalized asset and dependency graph to Neo4j AuraDB. |
| `scripts/verify_neo4j_graph.*` | Verify the latest Neo4j graph publication. |
| `scripts/query_sqlserver_fixture.*` | Inspect the local SQL Server fixture without SSMS. |
| `src/modern_migration_accelerator/pipelines/run_accelerator.py` | Serverless-safe assessment entrypoint. |
| `src/modern_migration_accelerator/pipelines/run_target_demo.py` | Demo consumer of the generated blueprint. |
| `src/modern_migration_accelerator/pipelines/run_semantic_index_prep.py` | Builds sanitized chunks from legacy artifacts and generated outputs. |
| `src/modern_migration_accelerator/neo4j_graph.py` | Builds and publishes the Neo4j graph payload. |

## Execution Order

1. Configure `.env`.
2. Run local smoke tests.
3. Optional: start SQL Server fixture and export metadata.
4. Validate the Databricks bundle.
5. Deploy the dev bundle.
6. Run the accelerator.
7. Review gold and control tables.
8. Run the target demo.
9. Prepare semantic chunks.
10. Create and query the Vector Search index.
11. Publish to Neo4j.
12. Add RAG and MLflow-backed workflows after retrieval behavior is trusted.

## Metadata Modes

Demo mode:

- Leave `LEGACY_METADATA_SOURCE_ROOT` empty.
- `scripts/run_accelerator_dev.sh` uploads `samples/legacy_metadata` to `/Volumes/<catalog>/landing/legacy_metadata/demo`.
- If `local_outputs/legacy_metadata` exists, it is uploaded into the same demo root.

Customer mode:

- Put customer exports in `/Volumes/<catalog>/landing/legacy_metadata/`.
- Set `LEGACY_METADATA_SOURCE_ROOT` to that path.
- Run the same bundle commands.

The customer does not need an existing metadata framework. The accelerator creates the normalized metadata model from raw exports.

## Output Model

| Layer | Tables |
| --- | --- |
| `control` | `run_log`, `metadata_snapshots` |
| `bronze` | `raw_metadata` |
| `silver` | `assets`, `dependencies` |
| `gold` | `assessment_summary`, `asset_priority_matrix`, `graph_edges`, `risk_register`, `target_databricks_blueprint`, `data_quality_plan`, `semantic_legacy_documents` |
| `demo` | `target_migration_plan` |

Read results in this order:

1. `gold.assessment_summary`
2. `gold.asset_priority_matrix`
3. `gold.graph_edges`
4. `gold.risk_register`
5. `gold.target_databricks_blueprint`
6. `gold.data_quality_plan`
7. `gold.semantic_legacy_documents`
8. `migration_accelerator_dev.gold.semantic_legacy_documents_vs`

## Product State

Confirmed working:

- Local SQL Server fixture, data inspection and metadata export.
- Databricks bundle validation, deployment and serverless jobs.
- Delta assessment outputs.
- Target demo table creation.
- Neo4j AuraDB graph publishing and verification.
- Semantic chunk table generation.
- Databricks Vector Search endpoint, Delta Sync hybrid index and query scripts.

Remaining product hardening:

- Add a small RAG/search utility on top of Vector Search.
- Add MLflow tracing and evaluation once generated answers are introduced.
- Add Databricks secret scope setup for enterprise credentials.
- Add customer-specific CI/CD only when the target toolchain is known.
- Add richer source-specific extractors as real customer artifacts reveal gaps.
