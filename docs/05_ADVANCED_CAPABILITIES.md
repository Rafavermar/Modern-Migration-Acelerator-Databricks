# Advanced Capabilities

The first Databricks run must produce trusted Delta outputs. Neo4j, Vector Search, RAG, MLflow and Model Serving then build on those outputs.

These capabilities are part of the full solution, but they require the Full Trial workspace, AuraDB credentials, security approval and customer decisions before activation.

## Phase Order

1. Databricks metadata assessment.
2. Neo4j graph exploration.
3. Vector Search and semantic legacy search.
4. RAG over legacy artifacts and generated blueprints.
5. MLflow tracing and evaluation for GenAI behavior.
6. Model Serving or agent endpoints for interactive assistant workflows.

## Readiness Gate

Do not activate these layers until:

- `silver.assets` is trusted.
- `silver.dependencies` is trusted.
- `gold.assessment_summary` is useful.
- `gold.asset_priority_matrix` is useful.
- `gold.graph_edges` is useful.
- `gold.risk_register` is reviewable.
- `gold.target_databricks_blueprint` is reviewable.
- Customer security approves graph publishing and indexing legacy documents.
- A retention and access policy exists for graph and indexed content.

## Neo4j

Purpose:

- Explore graph impact analysis interactively.
- Publish the accelerator asset and dependency model to a graph database.
- Keep Delta as the source of truth.

Needed:

- Neo4j URI and database name.
- Authentication method and secret location.
- TLS and network path from Databricks.
- Export mode: read-only graph publishing or bidirectional sync.

Local trial settings:

- AuraDB Professional Trial.
- 4GB memory when vector optimization is enabled.
- `neo4j+s://` URI.
- Password stored only in `.env` locally and later in Databricks secrets.

Initial labels:

- `MigrationRun`
- `MigrationAsset`
- `SourceSystem`
- `TargetPattern`

Initial relationships:

- `INCLUDES_ASSET`
- `FROM_SOURCE_SYSTEM`
- `HAS_TARGET_PATTERN`
- `MIGRATION_DEPENDENCY`

Local publish:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\publish_neo4j_graph.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\verify_neo4j_graph.ps1
```

The publisher reads the same metadata inputs as the demo run: `samples/legacy_metadata` plus `local_outputs/legacy_metadata` when SQL Server metadata has been exported. It enriches each asset with risk, priority, target pattern and DQ counts.

Useful Neo4j Browser queries:

```cypher
MATCH (r:MigrationRun)-[:INCLUDES_ASSET]->(a:MigrationAsset)
RETURN r, a
LIMIT 50;
```

```cypher
MATCH path = (a:MigrationAsset)-[:MIGRATION_DEPENDENCY*1..3]->(b:MigrationAsset)
WHERE a.review_priority = 'p1' OR a.risk_level = 'high'
RETURN path
LIMIT 25;
```

## Vector Search and RAG

Vector Search is the semantic retrieval layer. It lets a user ask questions such as "which high-risk order assets should move first?" and retrieve the most relevant chunks from legacy artifacts, risk rows, blueprint rows, graph edges and DQ plans.

Current base:

- `scripts/run_semantic_index_prep_dev.sh` creates `gold.semantic_legacy_documents`.
- `chunk_id` is the primary key.
- `chunk_text` is the text column to embed.
- Delta Change Data Feed is enabled on the table.
- `scripts/create_vector_search_dev.sh` creates a dev Vector Search endpoint and Delta Sync index.
- `scripts/query_vector_search_dev.sh` runs a starter semantic search.

Terminology:

| Term | Meaning in this project |
| --- | --- |
| Semantic corpus | `gold.semantic_legacy_documents`, the Delta table of sanitized searchable chunks. |
| Chunk | One row in `gold.semantic_legacy_documents`; each row has `chunk_id`, metadata and `chunk_text`. |
| Embedding | Numeric representation of `chunk_text`, computed by the Databricks embedding endpoint. |
| Embedding endpoint | `databricks-qwen3-embedding-0-6b`, the dev model endpoint that turns text into vectors. |
| Vector Search endpoint | `mma-vector-search-dev`, the serving endpoint for vector index queries. It is not a normal Model Serving endpoint. |
| Vector Search index | `migration_accelerator_dev.gold.semantic_legacy_documents_vs`, the Unity Catalog-managed searchable index. |
| Delta Sync | Databricks keeps the index aligned with a Delta source table. Dev uses triggered sync. |
| Hybrid search | Combines semantic vector retrieval with keyword matching. |

Purpose:

- Build embeddings over legacy documentation, ADF exports, Synapse notebooks, SQL scripts and generated blueprints.
- Support semantic search over the legacy estate.
- Support future RAG use cases such as "ask your legacy platform".
- Improve mapping between legacy assets and Databricks target patterns.

Inputs:

- `bronze.raw_metadata`
- `silver.assets`
- `silver.dependencies`
- `gold.semantic_legacy_documents`
- `gold.target_databricks_blueprint`
- `gold.risk_register`
- `gold.data_quality_plan`
- External legacy documentation and notebooks

Outputs:

- Chunked legacy artifact and generated-output Delta table.
- Embedding-ready document view.
- Databricks Vector Search index.
- Search notebook or API utility.
- RAG prompt template.

Activation steps:

1. Confirm which artifacts can be indexed.
2. Run `bash scripts/run_semantic_index_prep_dev.sh`.
3. Use embedding endpoint `databricks-qwen3-embedding-0-6b` for dev unless the customer mandates another model.
4. Run `bash scripts/create_vector_search_dev.sh`.
5. Query with `bash scripts/query_vector_search_dev.sh "<question>"`.
6. Add a search notebook, API utility or RAG workflow after the retrieval behavior is useful.

Dev Vector Search configuration:

- endpoint: `mma-vector-search-dev`
- endpoint type: `STANDARD`
- source table: `migration_accelerator_dev.gold.semantic_legacy_documents`
- index: `migration_accelerator_dev.gold.semantic_legacy_documents_vs`
- index type: `DELTA_SYNC`
- index subtype: `HYBRID`
- sync mode: `TRIGGERED`
- primary key: `chunk_id`
- embedding source column: `chunk_text`
- embedding endpoint: `databricks-qwen3-embedding-0-6b`

How it is implemented:

1. `run_semantic_index_prep.py` reads the latest successful accelerator run.
2. It loads source artifacts from the configured metadata root.
3. It sanitizes JSON and notebook content so sensitive keys are redacted before indexing.
4. It chunks source artifacts and generated Delta outputs into `gold.semantic_legacy_documents`.
5. It enables Delta Change Data Feed on that table.
6. `create_vector_search_dev.*` creates `mma-vector-search-dev`.
7. The script creates `migration_accelerator_dev.gold.semantic_legacy_documents_vs` as a `DELTA_SYNC` and `HYBRID` index.
8. Databricks computes embeddings from `chunk_text` with `databricks-qwen3-embedding-0-6b`.
9. The script waits until the index is ready and triggers sync.
10. `query_vector_search_dev.*` queries the REST endpoint and returns relevant chunks with scores.

How to use it:

Use Git Bash for the `.sh` job runner on Windows:

```powershell
& 'C:\Program Files\Git\bin\bash.exe' scripts/run_semantic_index_prep_dev.sh
```

Create or sync the index:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\create_vector_search_dev.ps1
```

Query it:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\query_vector_search_dev.ps1 -Query "Which high risk legacy assets should be migrated first?"
```

Where to see it in Databricks:

- Source table: `Catalog` > `migration_accelerator_dev` > `gold` > `semantic_legacy_documents`.
- Vector index: `Catalog` search for `semantic_legacy_documents_vs`, or browse `migration_accelerator_dev.gold`.
- Sync status: open the vector index, then use the `Overview` and `Data Ingest` section.
- Endpoint: verify with `databricks --profile <profile> vector-search-endpoints get-endpoint mma-vector-search-dev`.
- Do not look for `mma-vector-search-dev` under `AI/ML > Serving`; Vector Search endpoints are managed separately from normal serving endpoints.

Operational notes:

- First provisioning can take several minutes.
- The dev script waits for `ready=true` before querying.
- Query scripts call the Vector Search REST endpoint through `databricks api post` to avoid a current CLI wrapper parsing issue.
- For production, review endpoint type, sync mode, model endpoint, usage policy and service principal authentication.
- In dev, `indexed_row_count=309` was validated after indexing the demo estate plus SQL Server export.

Pause implementation if:

- The customer forbids indexing source code or documentation.
- Metadata is too incomplete to produce useful search.
- Existing enterprise search already covers the need.
- There is no workflow beyond "it would be nice to search".

## MLflow

Use MLflow when the accelerator introduces GenAI behavior or generated recommendations.

Track:

- Prompt versions.
- Retrieval context.
- Generated blueprint suggestions.
- Human review outcomes.
- Evaluation datasets.
- Trace spans for RAG or agent workflows.
- Quality metrics such as groundedness, correctness and completeness.

Pause implementation if:

- The accelerator remains deterministic.
- Recommendations are generated only by rules and Delta transforms.
- The customer has no process for reviewing GenAI outputs.
- The customer cannot approve storage of prompts, traces or retrieved context.

## Model Serving

Use Model Serving when users need an interactive assistant or recommendation endpoint.

Keep batch assessment in Databricks jobs and Delta outputs. Serving is for interactive workflows.

## Stop Conditions

Stop advanced work if:

- Source metadata is incomplete.
- Customer has not approved indexing sensitive artifacts.
- There is no clear user workflow for semantic search or RAG.
- Deterministic outputs are not yet trusted.
- The customer already has a platform that fully covers the need.

## Product Principle

Advanced capabilities must enhance the assessment while keeping the first-run Databricks path reliable and repeatable.

## Official References

- Databricks Vector Search setup: https://docs.databricks.com/aws/en/vector-search/create-vector-search
- Databricks Vector Search CLI: https://docs.databricks.com/aws/en/dev-tools/cli/reference/vector-search-indexes-commands
- Databricks Vector Search cost management: https://docs.databricks.com/aws/en/vector-search/vector-search-cost-management
