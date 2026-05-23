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

Neo4j is the interactive graph layer for migration impact analysis. It does not replace Delta tables; it gives architects a fast way to traverse dependencies, upstream/downstream blast radius and target-pattern clusters.

Role in the solution:

- Delta remains the source of truth: `silver.assets`, `silver.dependencies`, `gold.graph_edges`.
- Neo4j receives a published projection of the latest normalized graph.
- Users query Neo4j when they need path exploration, visual dependency maps or impact analysis.

Local trial configuration:

- AuraDB Professional Trial, instance `mma-graph-dev`.
- 4GB memory and vector-optimized configuration are acceptable for the trial.
- `neo4j+s://` URI.
- Password stored only in `.env` locally; use Databricks secrets or a customer secret manager for enterprise runs.

Implementation:

1. `publish_neo4j_graph.*` reads the same metadata inputs as the demo/customer run.
2. It parses assets, dependencies, risks, target patterns and DQ counts locally.
3. It writes a clean graph projection to AuraDB.
4. It uses constraints and `MERGE` so repeated publishes update the graph without duplicating nodes.
5. `verify_neo4j_graph.*` checks that the expected labels and relationships exist.

Graph model:

| Item | Meaning |
| --- | --- |
| `MigrationRun` | One publication run and its timestamp. |
| `MigrationAsset` | ADF pipeline, dataset, Synapse table, notebook, SQL script, SQL Server table or generated asset. |
| `SourceSystem` | Source platform grouping such as ADF, Synapse or SQL Server. |
| `TargetPattern` | Recommended Databricks target pattern. |
| `INCLUDES_ASSET` | Connects a run to its published assets. |
| `FROM_SOURCE_SYSTEM` | Groups assets by legacy platform. |
| `HAS_TARGET_PATTERN` | Shows the recommended target landing pattern. |
| `MIGRATION_DEPENDENCY` | Direct dependency between two assets. |

Publish and verify:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\publish_neo4j_graph.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\verify_neo4j_graph.ps1
```

Open Neo4j Aura Console > Query or Explore and run:

```cypher
MATCH (r:MigrationRun)-[:INCLUDES_ASSET]->(a:MigrationAsset)
RETURN r.run_id, count(a) AS assets
ORDER BY r.run_timestamp DESC
LIMIT 5;
```

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

Interpretation:

- Start with `MigrationRun` to confirm the latest publish.
- Use `review_priority='p1'` and `risk_level='high'` to find the migration review backlog.
- Expand `MIGRATION_DEPENDENCY` paths to see blast radius.
- Compare `TargetPattern` clusters with `gold.target_databricks_blueprint`.
- If Neo4j disagrees with Delta outputs, fix the accelerator parsing/model first and republish.

Screenshots can later be stored under `docs/assets/` and linked here.

## Vector Search and RAG

Vector Search is the semantic retrieval layer. It lets a user ask questions such as "which high-risk order assets should move first?" and retrieve relevant chunks from legacy artifacts, risk rows, blueprint rows, graph edges and DQ plans.

Role in the solution:

- `gold.semantic_legacy_documents` is the governed corpus.
- `semantic_legacy_documents_vs` is the retrieval index.
- `rag_search_dev.*` converts raw search results into a reviewer-friendly evidence brief.
- A later assistant should retrieve first, generate second, and log/evaluate every answer.

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
| ANN | Approximate nearest neighbor search over embedding vectors. Databricks Vector Search uses HNSW and L2 distance for ANN retrieval. |
| L2 distance | Euclidean distance between vectors. Lower distance means closer vectors. |
| Cosine similarity | Angle-based similarity. If self-managed embeddings need cosine-equivalent ranking, normalize vectors before indexing and querying. |
| Hybrid search | Combines semantic vector retrieval with keyword matching. |
| Reciprocal Rank Fusion | Ranking method used by Databricks hybrid search to merge ANN and full-text results. |
| Reranker | Optional second pass that can re-score retrieved rows for higher precision when latency and cost allow it. |
| RAG | Retrieval-augmented generation. In this repo the first layer retrieves and summarizes evidence before any LLM is added. |

Purpose:

- Build embeddings over legacy documentation, ADF exports, Synapse notebooks, SQL scripts and generated blueprints.
- Support semantic search over the legacy estate.
- Support RAG use cases such as "ask your legacy platform".
- Improve mapping between legacy assets and Databricks target patterns.

Inputs:

- `bronze.raw_metadata`
- `silver.assets`
- `silver.dependencies`
- `gold.target_databricks_blueprint`
- `gold.risk_register`
- `gold.data_quality_plan`
- External legacy documentation and notebooks

Outputs:

- `gold.semantic_legacy_documents`: chunked legacy artifact and generated-output Delta table.
- Databricks Vector Search index.
- `local_outputs/rag/latest_search.json`: raw search results.
- `local_outputs/rag/latest_answer.md`: grounded retrieval brief.
- `local_outputs/rag/latest_trace.json`: MLflow-ready trace payload.

Activation steps:

1. Confirm which artifacts can be indexed.
2. Run `bash scripts/run_semantic_index_prep_dev.sh`.
3. Use embedding endpoint `databricks-qwen3-embedding-0-6b` for dev unless the customer mandates another model.
4. Run `bash scripts/create_vector_search_dev.sh`.
5. Query with `bash scripts/query_vector_search_dev.sh "<question>"`.
6. Build a retrieval brief with `scripts/rag_search_dev.*`.
7. Add LLM generation only after retrieval quality is useful.

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
- ANN algorithm and distance: Databricks-managed HNSW with L2 distance
- query type: `HYBRID` by default in repo scripts

How it is implemented:

1. `run_semantic_index_prep.py` reads the latest successful accelerator run.
2. It loads source artifacts from the configured metadata root.
3. It sanitizes JSON and notebook content so sensitive keys are redacted before indexing.
4. It chunks source artifacts and generated Delta outputs into `gold.semantic_legacy_documents`.
5. It enables Delta Change Data Feed on that table.
6. `create_vector_search_dev.*` creates `mma-vector-search-dev`.
7. The script creates `migration_accelerator_dev.gold.semantic_legacy_documents_vs` as a `DELTA_SYNC` and `HYBRID` index.
8. Databricks computes embeddings from `chunk_text` with `databricks-qwen3-embedding-0-6b`.
9. The same embedding endpoint is used at query time when the user passes `query_text`.
10. The script waits until the index is ready and triggers sync.
11. `query_vector_search_dev.*` queries the REST endpoint and returns relevant chunks.
12. `rag_search_dev.*` parses those rows and writes a deterministic evidence brief plus trace JSON.

Metric and model alignment:

- HNSW is the ANN index/search algorithm. L2 distance is the vector distance used by Databricks Vector Search. They are not claims about how the embedding model was trained.
- In this dev index, metric selection is not a repo parameter. Databricks Vector Search uses HNSW with L2 distance for ANN retrieval.
- We ensure model/query consistency by using managed embeddings: Databricks embeds `chunk_text` and embeds `query_text` with the same configured endpoint, `databricks-qwen3-embedding-0-6b`.
- If a customer switches to self-managed embeddings or `query_vector`, the indexed vectors and query vectors must come from the same embedding model, same dimensions and same preprocessing.
- If the customer expects cosine-style similarity with self-managed vectors, normalize vectors before indexing and querying; normalized vectors make L2 ranking equivalent to cosine ranking.
- `HYBRID` search adds keyword/full-text matching and merges it with ANN ranking. Use it when questions include asset names, table names, technical terms or platform-specific jargon.
- Start with `num_results=5` for demos. Increase only when reviewers need broader evidence, because more results increase latency and cost.

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

Build a RAG-ready brief:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\rag_search_dev.ps1 -Question "Which high risk legacy assets should be migrated first?"
```

Where to see it in Databricks:

- Source table: `Catalog` > `migration_accelerator_dev` > `gold` > `semantic_legacy_documents`.
- Vector index: `Catalog` search for `semantic_legacy_documents_vs`, or browse `migration_accelerator_dev.gold`.
- Sync status: open the vector index, then use the `Overview` and `Data Ingest` section.
- Endpoint: verify with `databricks --profile <profile> vector-search-endpoints get-endpoint mma-vector-search-dev`.
- Do not look for `mma-vector-search-dev` under `AI/ML > Serving`; Vector Search endpoints are managed separately from normal serving endpoints.

Screenshot-friendly verification commands:

```powershell
databricks --profile mma-fulltrial vector-search-endpoints get-endpoint mma-vector-search-dev
databricks --profile mma-fulltrial vector-search-indexes get-index migration_accelerator_dev.gold.semantic_legacy_documents_vs
powershell -ExecutionPolicy Bypass -File .\scripts\query_vector_search_dev.ps1 -Query "Which high risk assets should be migrated first?"
powershell -ExecutionPolicy Bypass -File .\scripts\rag_search_dev.ps1 -Question "Which high risk assets should be migrated first?"
```

Programmatic query options:

- Repo script: `scripts/query_vector_search_dev.*`.
- Repo RAG utility: `scripts/rag_search_dev.*`.
- Databricks REST API: `POST /api/2.0/vector-search/indexes/<index_name>/query`.
- Databricks SQL: `vector_search()` when enabled in the target workspace.
- Python SDK: useful later for notebooks or a served app.

Interpretation:

- A result is evidence, not a final recommendation.
- `asset_name`, `risk_level`, `review_priority` and `target_pattern` explain why a chunk is useful.
- `source_path` tells you whether evidence came from raw legacy metadata or generated gold outputs.
- Strong migration decisions should be confirmed in `gold.asset_priority_matrix`, `gold.risk_register`, `gold.graph_edges` and Neo4j.
- Weak or generic results mean the semantic corpus needs better artifacts, richer metadata exports or more specific user questions.

Operational notes:

- First provisioning can take several minutes.
- The dev script waits for `ready=true` before querying.
- Query scripts call the Vector Search REST endpoint through `databricks api post` to avoid a current CLI wrapper parsing issue.
- For production, review endpoint type, sync mode, model endpoint, usage policy and service principal authentication.
- In dev, `indexed_row_count=309` was validated after indexing the demo estate plus SQL Server export.
- Query scripts use `HYBRID` by default because migration questions often mix natural language and exact asset names.

Pause implementation if:

- The customer forbids indexing source code or documentation.
- Metadata is too incomplete to produce useful search.
- Existing enterprise search already covers the need.
- There is no workflow beyond "it would be nice to search".

## MLflow

MLflow is the observability and evaluation layer for GenAI behavior. The current RAG utility creates a trace-shaped JSON payload and can optionally log artifacts to an MLflow experiment. Full MLflow GenAI tracing starts when an LLM response is introduced.

Current starter:

- Optional dependency: `pip install -e .[genai]`.
- Experiment: `MLFLOW_EXPERIMENT_NAME`, default `/Shared/modern-migration-accelerator`.
- Script: `scripts/rag_search_dev.ps1 -LogMlflow`.
- Logged artifacts: search JSON, retrieval brief and trace JSON.

Trace and evaluate when generated answers exist:

- Prompt versions.
- Retrieval context.
- Generated blueprint suggestions.
- Human review outcomes.
- Evaluation datasets.
- Trace spans for RAG or agent workflows.
- Quality metrics such as groundedness, correctness and completeness.

Minimal evaluation path:

1. Curate 10-20 real migration questions.
2. Store expected answer notes and reviewer expectations.
3. Run the RAG/assistant workflow with MLflow tracing enabled.
4. Evaluate relevance, groundedness, safety and completeness.
5. Promote only prompts/models that improve the evaluation set.

Where to see it in Databricks:

- `Experiments` for MLflow runs and artifacts.
- Evaluation runs after `mlflow.genai.evaluate()` is introduced.
- Traces once the RAG function or assistant endpoint is instrumented.

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
- Databricks Vector Search query options: https://docs.databricks.com/aws/en/vector-search/query-vector-search
- Databricks Vector Search CLI: https://docs.databricks.com/aws/en/dev-tools/cli/reference/vector-search-indexes-commands
- Databricks Vector Search cost management: https://docs.databricks.com/aws/en/vector-search/vector-search-cost-management
- Databricks MLflow Tracing for GenAI: https://docs.databricks.com/aws/en/mlflow3/genai/tracing/
- Databricks MLflow GenAI evaluation: https://docs.databricks.com/aws/en/mlflow3/genai/eval-monitor/concepts/eval-harness
