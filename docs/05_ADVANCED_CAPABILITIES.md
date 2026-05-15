# Advanced Capabilities

The MVP must remain deterministic and useful without Vector Search, GenAI, MLflow, Model Serving or Neo4j.

These capabilities should be added only after the first Databricks run produces trusted Delta outputs.

## Phase Order

1. MVP metadata assessment.
2. Neo4j graph exploration, optional.
3. Vector Search and semantic legacy search.
4. RAG over legacy artifacts and generated blueprints.
5. MLflow tracing and evaluation for GenAI behavior.
6. Model Serving or agent endpoints, only if users need an interactive assistant.

## Readiness Gate

Do not start advanced phases until:

- `silver.assets` is trusted.
- `silver.dependencies` is trusted.
- `gold.risk_register` is reviewable.
- `gold.target_databricks_blueprint` is reviewable.
- Customer security approves indexing legacy documents.
- A retention and access policy exists for indexed content.

## Neo4j

Purpose:

- Explore graph impact analysis interactively.
- Publish `silver.assets` and `silver.dependencies` to a graph database.
- Keep Delta as the source of truth.

Needed later:

- Neo4j URI and database name.
- Authentication method and secret location.
- TLS and network path from Databricks.
- Export mode: read-only graph publishing or bidirectional sync.

Initial labels:

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

## Vector Search and RAG

Purpose:

- Build embeddings over legacy documentation, ADF exports, Synapse notebooks, SQL scripts and generated blueprints.
- Support semantic search over the legacy estate.
- Support future RAG use cases such as "ask your legacy platform".
- Improve mapping between legacy assets and Databricks target patterns.

Inputs:

- `bronze.raw_metadata`
- `silver.assets`
- `silver.dependencies`
- `gold.target_databricks_blueprint`
- `gold.risk_register`
- `gold.data_quality_plan`
- External legacy documentation and notebooks

Future outputs:

- Chunked legacy artifact Delta table.
- Embedding-ready document view.
- Databricks Vector Search index.
- Search notebook or API utility.
- Optional RAG prompt template.

Do not implement if:

- The customer forbids indexing source code or documentation.
- Metadata is too incomplete to produce useful search.
- Existing enterprise search already covers the need.
- There is no workflow beyond "it would be nice to search".

## MLflow

Use MLflow only if the accelerator introduces GenAI behavior.

Track:

- Prompt versions.
- Retrieval context.
- Generated blueprint suggestions.
- Human review outcomes.
- Evaluation datasets.
- Trace spans for RAG or agent workflows.
- Quality metrics such as groundedness, correctness and completeness.

Do not implement if:

- The accelerator remains deterministic.
- Recommendations are generated only by rules and Delta transforms.
- The customer has no process for reviewing GenAI outputs.
- The customer cannot approve storage of prompts, traces or retrieved context.

## Model Serving

Use Model Serving only if users need an interactive assistant or recommendation endpoint.

Do not use it for the batch MVP. Databricks jobs and Delta outputs are enough for first-run assessment.

## Stop Conditions

Stop advanced work if:

- Source metadata is incomplete.
- Customer has not approved indexing sensitive artifacts.
- There is no clear user workflow for semantic search or RAG.
- Deterministic outputs are not yet trusted.
- The customer already has a platform that fully covers the need.

## Product Principle

Advanced features should enhance the assessment. They should not become mandatory dependencies for running the accelerator.
