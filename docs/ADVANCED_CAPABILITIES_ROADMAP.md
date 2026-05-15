# Advanced Capabilities Roadmap

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

## Advanced Capability Scope

Vector Search:

- Index legacy documents, code, metadata and blueprints.
- Support semantic discovery and future RAG.
- Not required for deterministic risk scoring.

MLflow:

- Track prompts, traces, evals and GenAI experiments.
- Not required for Delta control tables or job logs.

Model Serving:

- Serve an assistant or recommendation endpoint.
- Not required for batch migration assessment.

Neo4j:

- Explore graph impact analysis interactively.
- Not the source of truth; Delta remains authoritative.

## Stop Conditions

Stop advanced work if:

- Source metadata is incomplete.
- Customer has not approved indexing sensitive artifacts.
- There is no clear user workflow for semantic search or RAG.
- Deterministic outputs are not yet trusted.
- The customer already has a platform that fully covers the need.

## Product Principle

Advanced features should enhance the assessment. They should not become mandatory dependencies for running the accelerator.
