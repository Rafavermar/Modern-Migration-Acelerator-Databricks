# Demo And Packaging

Internal guide for screenshots, walkthroughs, release packaging and promo video planning.

Use this document only after the end-to-end dev flow is green.

## Finished Product Boundary

The finished sellable product is:

- a Databricks migration assessment and planning accelerator;
- a plug-and-play metadata landing and bundle execution flow;
- a Delta output model for inventory, dependencies, risks, priorities, blueprint and DQ plan;
- Neo4j impact graph publishing;
- Vector Search, RAG, Foundation Model answer generation, MLflow logging and starter RAG eval;
- documentation that explains demo mode, customer mode and migration execution boundaries.

The remaining improvements are customer-dependent:

- richer extractors for real ADF/Synapse/SQL/notebook patterns;
- customer-specific scoring weights;
- customer-specific secret scopes, service principals and CI/CD;
- production ingestion/federation patterns after the assessment;
- optional served assistant endpoint if the customer needs an interactive API.

Do not block the walkthrough on those items.

## Product Readiness Gate

The product is demo-ready when these checks pass:

- `scripts/local_smoke_test.*` passes.
- Databricks bundle validates and deploys.
- Accelerator job writes `control`, `bronze`, `silver` and `gold` tables.
- Target demo writes `demo.target_migration_plan`.
- Neo4j publish and verify scripts pass.
- Semantic prep writes `gold.semantic_legacy_documents`.
- Vector Search index is ready and synced.
- RAG search returns grounded evidence.
- LLM answer generation works with the configured Foundation Model endpoint.
- MLflow logs retrieval/generation artifacts.
- RAG eval passes the starter cases.
- README and docs explain assessment scope, execution boundary and customer mode.

This is sellable as a migration assessment and planning accelerator. It is not sold as an automatic data migration engine.

## RAG Serving Decision

Current product mode:

- `rag_search_dev.*` is the validated reviewer workflow.
- `-GenerateAnswer` calls the Databricks Foundation Model endpoint.
- `-LogMlflow` records evidence and generated-answer artifacts.
- This is enough for demo, workshops and assessment delivery.

When to add Model Serving or AI Gateway:

- users need an interactive assistant instead of a script;
- another app must call the accelerator through an API;
- access, rate limits, monitoring and endpoint ownership are approved;
- the customer accepts serving endpoint cost and lifecycle management.

Recommended serving path:

1. Package the RAG workflow as an MLflow `pyfunc` or agent-style model.
2. Register it in Unity Catalog.
3. Create a Databricks Model Serving endpoint.
4. Configure secrets/service principal access to Vector Search, MLflow and the Foundation Model endpoint.
5. Add AI Gateway policies if the customer requires governance, rate limits or monitoring.

Do not make a served endpoint mandatory for the core product. It is an enterprise delivery option on top of the validated assessment workflow.

## Screenshot Checklist

Save screenshots under `docs/assets/`. Use short lowercase names.

| File | Capture |
| --- | --- |
| `databricks_jobs.png` | Jobs & Pipelines with accelerator, target demo and semantic prep jobs. |
| `catalog_gold_tables.png` | Catalog view showing `gold` tables. |
| `assessment_summary.png` | `gold.assessment_summary` result. |
| `priority_matrix.png` | `gold.asset_priority_matrix` filtered or sorted by priority. |
| `target_blueprint.png` | `gold.target_databricks_blueprint`. |
| `vector_search_index.png` | `semantic_legacy_documents_vs` in Catalog with sync status. |
| `rag_search_terminal.png` | RAG search command output. |
| `mlflow_run.png` | MLflow run with RAG artifacts. |
| `neo4j_graph.png` | Neo4j graph view with `MigrationAsset` nodes and dependencies. |
| `rag_eval.png` | `rag_eval_dev.ps1` summary showing pass count. |

After screenshots are added, link only the most useful ones in README and architecture docs. Do not overload the docs with every capture.

## Screenshot Privacy Gate

Do not commit public screenshots that expose:

- personal email addresses;
- customer names;
- workspace URLs or organization IDs;
- tokens, passwords or secret names;
- private hostnames, tenant IDs or billing details.

Use raw screenshots for local study and internal rehearsal only. For public docs, product pages or releases, create a sanitized screenshot set with redacted workspace identity and customer-specific values. Keep the public repo useful without leaking delivery-environment details.

## Manual Demo Flow

Use one clean terminal and one browser profile.

1. Start with the README: explain that this is an assessment accelerator.
2. Show `.env.example`: point out replaceable connection points, not secrets.
3. Run local smoke test.
4. Show Databricks jobs already deployed.
5. Run or show the accelerator job result.
6. Open Catalog and inspect `gold.assessment_summary`.
7. Open `gold.asset_priority_matrix` and explain first-wave review.
8. Open `gold.graph_edges` or Neo4j and explain impact analysis.
9. Open `gold.target_databricks_blueprint` and explain migration pattern decisions.
10. Open `gold.data_quality_plan` and explain validation backlog.
11. Show Vector Search index and run one semantic query.
12. Run RAG search with `-GenerateAnswer -LogMlflow`.
13. Open MLflow run artifacts.
14. Run RAG eval and show pass summary.
15. Close with customer mode: upload artifacts to the landing volume and set `LEGACY_METADATA_SOURCE_ROOT`.

## Promo Video Storyline

Keep the video focused on the buyer problem.

1. Legacy estate is fragmented across ADF, Synapse, SQL Server, notebooks and SQL.
2. The customer exports metadata instead of granting production data access first.
3. The accelerator runs in Databricks as a bundle.
4. Delta outputs reveal inventory, dependencies, risk, priorities, blueprint and DQ plan.
5. Neo4j shows impact visually.
6. Vector Search and RAG answer migration questions over the estate.
7. MLflow records generated-answer evidence.
8. The result is a reviewed migration backlog and target plan, ready for engineering execution.

Avoid claiming automatic migration. Say: "It accelerates the decision layer that makes migration execution safer."

## Packaging Options

Recommended now:

- GitHub repository template plus Databricks Asset Bundle.
- Versioned GitHub releases with source zip and clear release notes.
- `.env.example`, sample metadata, contracts and scripts included.
- Customer clones the repo, fills `.env`, runs the documented commands and replaces metadata inputs.

Plain meaning:

- GitHub repository template: users can create their own copy of the project without copying secrets or local state.
- Databricks Asset Bundle: the deployable unit that creates the Databricks jobs and keeps resources defined as code.
- Versioned release: a tagged stable snapshot such as `v0.1.0` with release notes, so demos and customers do not depend on a moving branch.
- Customer overlay: customer-specific values live outside the base product, usually in `.env`, bundle variables, secret scopes or a private fork.

Good enterprise package:

- Private customer fork or internal template repo.
- Customer-specific config overlay for catalog, workspace, landing path and secret scope.
- CI/CD added by the customer toolchain.
- No credentials or customer artifacts committed.

Public solution package:

- Publish as a Databricks solution accelerator style repo.
- Include screenshots, demo video, sample metadata and a tagged release.
- Keep Databricks Asset Bundle as the deployment unit.

Later productized package:

- Add a small CLI wrapper around the scripts.
- Add a customer config file instead of many environment variables.
- Add optional Model Serving or AI Gateway assistant endpoint.
- Add scorer-based MLflow GenAI evaluation.

Best near-term choice: keep the Databricks Asset Bundle as the core package, distribute through GitHub releases, and use customer-specific forks or overlays for enterprise implementation.
