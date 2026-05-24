# Creator Operating Guide

Internal guide for understanding, explaining and evolving the Modern Migration Accelerator.

This is not customer onboarding documentation. It is the creator map: what we built, why it exists, how the pieces interact, where friction was removed and what becomes customer-specific later.

## Product In One Sentence

The accelerator turns exported legacy metadata into a Databricks-native migration assessment: inventory, dependencies, risk, priorities, target blueprint, data quality plan, graph exploration, semantic search and grounded RAG evidence.

It helps teams decide and plan migration. It does not automatically move all production data, convert every pipeline or execute cutover.

## Current Product Shape

Current validated flow:

1. Configure `.env`.
2. Land sample or customer metadata in a Unity Catalog volume.
3. Deploy Databricks jobs with the Asset Bundle.
4. Run the assessment job.
5. Review Delta outputs.
6. Run the target blueprint demo.
7. Publish the graph to Neo4j.
8. Prepare semantic chunks.
9. Create/sync Databricks Vector Search.
10. Ask migration questions through RAG search.
11. Generate grounded answers with a Databricks Foundation Model endpoint.
12. Log evidence and generated outputs to MLflow.
13. Run starter RAG evaluation cases.

Why this is the right MVP:

- It proves the core assessment value.
- It avoids requiring production data movement on day one.
- It keeps every output reviewable in Delta, Neo4j, Vector Search and MLflow.
- It is easy to demo and easy to adapt to a real customer estate.

## Programmatic Execution Flow

This is the concrete call chain from terminal command to Databricks outputs.

Local setup:

```text
scripts/setup_dev_env.* -> creates/updates .venv -> installs package extras when requested
scripts/local_smoke_test.* -> compiles Python -> parses sample metadata -> runs unit tests
```

Databricks deploy:

```text
scripts/deploy_dev.sh
  -> scripts/lib/load_env.sh reads .env
  -> sets BUNDLE_VAR_catalog and BUNDLE_VAR_source_root
  -> scripts/upload_sample_metadata_dev.sh
      -> creates schema <catalog>.landing if missing
      -> creates volume <catalog>.landing.legacy_metadata if missing
      -> uploads runtime Python files to /Volumes/<catalog>/landing/legacy_metadata/runtime/
      -> uploads samples/legacy_metadata to /Volumes/<catalog>/landing/legacy_metadata/demo when customer source is not set
      -> uploads local_outputs/legacy_metadata when SQL Server export exists
  -> databricks bundle deploy -t dev
      -> reads databricks.yml
      -> reads resources/jobs.yml
      -> creates/updates Databricks jobs
```

Assessment run:

```text
scripts/run_accelerator_dev.sh
  -> reads .env
  -> if LEGACY_METADATA_SOURCE_ROOT is empty:
       sets source_root=/Volumes/<catalog>/landing/legacy_metadata/demo
       calls upload_sample_metadata_dev.sh
     else:
       sets source_root=<customer volume path>
  -> databricks bundle run migration_accelerator -t dev
      -> resources/jobs.yml task parse_analyze_blueprint
      -> spark_python_task runs dbfs:/Volumes/<catalog>/landing/legacy_metadata/runtime/run_accelerator.py
      -> run_accelerator.py reads source_root with Spark binaryFile
      -> parses JSON, CSV, SQL and notebook files
      -> normalizes assets and dependencies
      -> builds risk, priority, blueprint, graph and DQ outputs
      -> writes Delta tables in <catalog>.control, bronze, silver and gold
```

Target demo:

```text
scripts/run_target_demo_dev.sh
  -> databricks bundle run target_demo -t dev
      -> resources/jobs.yml task create_target_demo
      -> runs runtime/run_target_demo.py from the Unity Catalog volume
      -> reads gold.target_databricks_blueprint
      -> writes demo.target_migration_plan
```

Semantic prep:

```text
scripts/run_semantic_index_prep_dev.sh
  -> databricks bundle run semantic_index_prep -t dev
      -> resources/jobs.yml task prepare_semantic_documents
      -> runs runtime/run_semantic_index_prep.py from the Unity Catalog volume
      -> reads source metadata and generated Delta outputs
      -> sanitizes and chunks text
      -> writes gold.semantic_legacy_documents
      -> enables Delta Change Data Feed for Vector Search sync
```

Vector Search:

```text
scripts/create_vector_search_dev.*
  -> reads .env
  -> gets or creates Vector Search endpoint mma-vector-search-dev
  -> gets or creates index migration_accelerator_dev.gold.semantic_legacy_documents_vs
  -> index source table is gold.semantic_legacy_documents
  -> embedding source column is chunk_text
  -> embedding endpoint is databricks-qwen3-embedding-0-6b
  -> waits for ready=true
  -> triggers sync
```

RAG retrieval and generated answer:

```text
scripts/rag_search_dev.ps1
  -> runs python -m modern_migration_accelerator.rag_search
  -> rag_search.py reads .env
  -> calls Databricks Vector Search REST API
  -> parses returned chunks
  -> writes local_outputs/rag/latest_search.json
  -> writes local_outputs/rag/latest_answer.md
  -> writes local_outputs/rag/latest_trace.json

scripts/rag_search_dev.ps1 -GenerateAnswer
  -> builds prompt from retrieved evidence only
  -> calls Databricks serving-endpoints query <DATABRICKS_LLM_ENDPOINT>
  -> writes latest_generation.json and latest_llm_answer.md

scripts/rag_search_dev.ps1 -LogMlflow
  -> sets MLflow tracking to databricks://<DATABRICKS_PROFILE>
  -> logs params, metrics and artifacts to /Shared/modern-migration-accelerator
```

RAG eval:

```text
scripts/rag_eval_dev.ps1
  -> runs python -m modern_migration_accelerator.rag_eval
  -> reads contracts/rag_eval_questions.json
  -> executes multiple RAG retrieval calls
  -> scores expected terms/assets against retrieved evidence
  -> writes local_outputs/rag_eval/latest_eval.json
  -> writes local_outputs/rag_eval/latest_eval.md
```

Neo4j graph:

```text
scripts/check_neo4j_connection.ps1
  -> verifies URI, auth and database

scripts/publish_neo4j_graph.ps1
  -> runs scripts/publish_neo4j_graph.py
  -> uses modern_migration_accelerator.neo4j_graph
  -> parses samples and optional local metadata outputs
  -> MERGE nodes/relationships into AuraDB

scripts/verify_neo4j_graph.ps1
  -> checks expected labels and relationship counts
```

Important design choice:

- Databricks jobs run code from `/Volumes/.../runtime/`, not from `/Workspace/.../.bundle/.../files`.
- Functional metadata lives in `/Volumes/.../legacy_metadata/`, not in the bundle files path.
- This makes the serverless path more reliable and closer to enterprise workspace rules.

## What Each Layer Does

Databricks assessment:

- Code: `src/modern_migration_accelerator/pipelines/run_accelerator.py`.
- Job: `modern_migration_accelerator_databricks-dev-accelerator`.
- Reads metadata from `LEGACY_METADATA_SOURCE_ROOT`.
- Writes `control`, `bronze`, `silver` and `gold` Delta tables.
- Produces the migration decision model.

Target demo:

- Code: `src/modern_migration_accelerator/pipelines/run_target_demo.py`.
- Job: `modern_migration_accelerator_databricks-dev-target-demo`.
- Reads `gold.target_databricks_blueprint`.
- Writes `demo.target_migration_plan`.
- Proves the blueprint can feed downstream jobs.
- Does not move production source data.

Neo4j:

- Code: `src/modern_migration_accelerator/neo4j_graph.py`.
- Scripts: `scripts/publish_neo4j_graph.*`, `scripts/verify_neo4j_graph.*`.
- Publishes `MigrationAsset`, `SourceSystem`, `TargetPattern` and dependency relationships.
- Used for visual impact analysis and dependency traversal.
- Delta remains the source of truth.

Semantic corpus:

- Code: `src/modern_migration_accelerator/pipelines/run_semantic_index_prep.py`.
- Job: `modern_migration_accelerator_databricks-dev-semantic-index-prep`.
- Writes `gold.semantic_legacy_documents`.
- Sanitizes and chunks source artifacts plus generated gold outputs.

Vector Search:

- Endpoint: `mma-vector-search-dev`.
- Index: `migration_accelerator_dev.gold.semantic_legacy_documents_vs`.
- Source table: `migration_accelerator_dev.gold.semantic_legacy_documents`.
- Text column: `chunk_text`.
- Primary key: `chunk_id`.
- Embedding endpoint: `databricks-qwen3-embedding-0-6b`.
- Query mode: `HYBRID`.
- Purpose: semantic and keyword retrieval over the migration estate.

RAG search:

- Code: `src/modern_migration_accelerator/rag_search.py`.
- Script: `scripts/rag_search_dev.*`.
- Retrieves evidence from Vector Search.
- Builds a deterministic reviewer brief.
- With `-GenerateAnswer`, calls `databricks-gemma-3-12b`.
- With `-LogMlflow`, logs evidence and generation artifacts to MLflow.

MLflow:

- Experiment default: `/Shared/modern-migration-accelerator`.
- Used for retrieval/generation artifacts and manual trace spans.
- Purpose: make generated answers auditable, not magical.

RAG eval:

- Code: `src/modern_migration_accelerator/rag_eval.py`.
- Script: `scripts/rag_eval_dev.*`.
- Cases: `contracts/rag_eval_questions.json`.
- Default mode is retrieval-only.
- Checks expected terms/assets appear in evidence.
- Useful as a demo regression check, not a full GenAI judge.

SQL Server fixture:

- Docker service: `legacy-sqlserver`.
- Container: `mma-legacy-sqlserver`.
- Volume: `legacy-sqlserver-data`.
- Scripts: `bootstrap`, `check`, `query`, `export`.
- Purpose: local repeatable SQL Server metadata simulation.
- Customers do not need Docker if they provide SQL Server exports.

## How To Interpret Results

Start here:

1. `gold.assessment_summary`: one-row executive summary.
2. `gold.asset_priority_matrix`: what should be reviewed first.
3. `gold.graph_edges`: what depends on what.
4. `gold.risk_register`: why an asset is risky.
5. `gold.target_databricks_blueprint`: recommended target pattern.
6. `gold.data_quality_plan`: validation backlog.
7. Neo4j: visual blast radius.
8. Vector Search/RAG: evidence search over raw artifacts and generated outputs.
9. MLflow: audit trail for RAG/generation runs.

The key message:

- Priority tells where to look first.
- Risk explains why.
- Graph shows what can break.
- Blueprint suggests how to migrate.
- DQ plan defines what to validate.
- RAG helps ask questions over the evidence.

## Demo Mode vs Customer Mode

Demo mode:

- `LEGACY_METADATA_SOURCE_ROOT` is empty.
- Scripts upload `samples/legacy_metadata`.
- Optional SQL Server export is included if `local_outputs/legacy_metadata` exists.
- Good for screenshots, video and first validation.

Customer mode:

- Customer exports files to `/Volumes/<catalog>/landing/legacy_metadata/`.
- Set `LEGACY_METADATA_SOURCE_ROOT=/Volumes/<catalog>/landing/legacy_metadata`.
- Same jobs, same outputs, different inputs.
- The customer does not need an existing metadata framework.

Customer artifacts should go under:

- `adf/`
- `synapse/inventory/`
- `synapse/notebooks/`
- `synapse/sql/`
- `sqlserver/inventory/`
- `docs/`

## Frictions We Removed

Workspace Files read errors:

- Problem: serverless jobs hit intermittent `OSError: [Errno 5]` reading bundle files under `/Workspace/...`.
- Fix: runtime scripts and metadata are uploaded to Unity Catalog volumes.

Public DBFS root disabled:

- Problem: governed workspaces can block `dbfs:/tmp`.
- Fix: use `/Volumes/<catalog>/landing/legacy_metadata`.

Git Bash path conversion:

- Problem: Git Bash rewrote `/Volumes/...` and `/api/...` into Windows paths.
- Fix: scripts set `MSYS_NO_PATHCONV=1` and `MSYS2_ARG_CONV_EXCL=*`.

Databricks Vector Search CLI query wrapper:

- Problem: the CLI wrapper could return unmarshalling errors.
- Fix: query scripts use `databricks api post` against the Vector Search REST API.

PowerShell Unicode with MLflow:

- Problem: MLflow run links could trigger encoding errors.
- Fix: RAG entrypoints configure stdout/stderr as UTF-8.

Databricks CLI Windows execution:

- Problem: Python subprocesses can hit `WinError 5` with CLI app aliases.
- Fix: RAG utilities resolve `DATABRICKS_CLI` or explicit `databricks.exe`.

SQL Server laptop reboot:

- Problem: uncertainty about Docker state after shutdown.
- Fix: SQL Server data lives in a named Docker volume. Open Docker Desktop and rerun bootstrap if stopped.

## What Still Depends On A Real Customer

Extractor depth:

- Need representative redacted artifacts.
- Examples: parameterized ADF, dynamic SQL, Synapse notebooks, stored procedure dependencies, custom naming conventions, Purview exports.
- Without real artifacts, inventing extractors creates fake confidence.

Scoring weights:

- Current rules are deterministic and useful.
- Customers may want criticality weights, owner weights, SLA weights or wave-planning rules.
- Those should be configured after stakeholder review.

Secrets and service principals:

- Local `.env` is fine for dev.
- Enterprise deployments need Databricks secret scopes, service principals and customer-approved policies.
- Exact setup depends on the customer identity model.

CI/CD:

- The bundle is CI/CD-ready.
- Workflow files are intentionally not included because approval gates, auth and environments are customer-specific.

Production migration execution:

- The accelerator recommends target patterns.
- The customer implements ingestion, federation, external tables, volumes, notebooks or jobs according to policy.

## RAG Serving Endpoint Option

Current mode:

```text
Question -> rag_search_dev.ps1 -> Vector Search -> Foundation Model -> local outputs + MLflow
```

This is enough for demos and assessment workshops because it is simple, visible and auditable.

Served mode would be:

```text
POST /serving-endpoints/mma-rag-assistant/invocations
{
  "question": "Which assets should migrate first?"
}
```

Internally, the endpoint would:

1. receive the question;
2. query Vector Search;
3. build the grounded prompt;
4. call the Foundation Model endpoint;
5. return the answer;
6. log evidence/traces if configured.

Implementation path:

1. Wrap the RAG logic as an MLflow `pyfunc` or Databricks agent-style model.
2. Log the model with code dependencies.
3. Register it in Unity Catalog.
4. Create a Databricks Model Serving endpoint.
5. Give the endpoint identity access to Vector Search and Foundation Model APIs.
6. Configure secrets/service principal access.
7. Test latency, cold start, permissions and cost.
8. Document request/response payloads.

Why we did not make it mandatory:

- It does not improve the core assessment outputs.
- It adds endpoint lifecycle and permissions.
- It adds cost and possible cold start.
- It makes demos more fragile.
- It is a delivery/exposure layer, not the value core.

When to build it:

- Customer asks for an API.
- Customer wants a portal, Teams bot, dashboard or workflow integration.
- There is an agreed owner for endpoint permissions, monitoring and cost.

## Packaging Decision

Near-term package:

- GitHub repository template or tagged release.
- Databricks Asset Bundle as deployment unit.
- `.env.example`, scripts, contracts and sample metadata as onboarding.
- Customer uses a private fork or configuration overlay.

Why:

- Simple to understand.
- Easy to version.
- Easy to demo.
- Does not hide Databricks resources behind a custom installer.

Enterprise package:

- Private fork/internal template.
- Customer-specific catalog, workspace, landing path and secret scope values.
- CI/CD from the customer standard toolchain.
- No customer artifacts or secrets in the base repo.

Later productized package:

- Thin CLI wrapper.
- Customer config file.
- Optional served RAG assistant endpoint.
- Scorer-based GenAI evaluation.
- More extractors driven by real artifacts.

## Multi-Client Operating Model

Keep two layers separate:

- Product base: this repository, versioned as releases such as `v0.1.0`.
- Customer implementation: a private fork, repo copy or configuration overlay with customer-specific metadata, secrets strategy and deployment settings.

Recommended flow for a new client:

1. Start from the latest product release.
2. Create a private customer repo or fork.
3. Configure `.env` or bundle variables for the customer workspace, catalog and landing volume.
4. Keep secrets outside Git: Databricks secrets, service principals or the customer secret manager.
5. Ask the customer for redacted metadata exports first.
6. Run demo/customer mode with those exports.
7. Review outputs with architects.
8. If extractors miss real patterns, add source-specific parser improvements in the customer branch.
9. Decide whether the improvement is generic.
10. If generic, port it back to the product base and release a new version.
11. If customer-specific, keep it only in the customer implementation.

How to distribute improvements:

- Patch release: bug fixes, docs, small parser fixes. Example: `v0.1.1`.
- Minor release: new source family, new output, improved RAG/eval workflow. Example: `v0.2.0`.
- Customer overlay update: merge the product release into the customer fork after testing.

What never goes back to the product base:

- customer credentials;
- customer metadata artifacts;
- customer hostnames, workspace IDs or tenant details;
- customer-specific scoring rules unless generalized and anonymized;
- screenshots with sensitive names unless sanitized.

If several clients exist:

- keep each implementation isolated;
- keep the product base clean;
- promote only reusable improvements;
- document migration notes in `CHANGELOG.md`;
- tag releases so clients can upgrade intentionally, not accidentally.

Practical example:

```text
modern-migration-accelerator          -> product base, public or controlled repo
client-a-mma-implementation           -> private implementation repo
client-b-mma-implementation           -> private implementation repo
```

Client A has custom ADF expressions. We improve the parser. If the logic is generally useful and sanitized, we add it to product base `v0.2.0`. Client B can later adopt `v0.2.0` without inheriting Client A data.

## Sources Used For The Serving Decision

Databricks custom Model Serving supports deploying Python custom code as production APIs through MLflow `pyfunc`, then registering and serving the model. Databricks also documents endpoint lifecycle considerations such as deployment time, scaling, scale-to-zero cold starts and cost/lifecycle implications.

Official references:

- Databricks custom models overview: https://docs.databricks.com/aws/en/machine-learning/model-serving/custom-models
- Databricks deploy Python code with Model Serving: https://docs.databricks.com/aws/en/machine-learning/model-serving/deploy-custom-python-code

## What To Say In A Demo

Say:

- "This accelerates assessment and migration planning."
- "It turns exports into a Databricks-native decision layer."
- "It tells us what to review first, why, what depends on it and what target pattern fits."
- "Actual data movement and code rebuild remain controlled engineering work."
- "If the customer needs an API, the RAG workflow can be packaged behind Model Serving."

Avoid saying:

- "This automatically migrates everything."
- "This replaces Purview or Unity Catalog governance."
- "This converts all ADF/Synapse logic."
- "This endpoint is required for the product to work."

## Current Completion Statement

Version `0.1.0` is complete for a sellable assessment MVP.

The next meaningful improvements should be driven by:

- screenshots and demo polish;
- real customer artifacts;
- customer security/deployment requirements;
- customer decision to expose RAG as an API.
