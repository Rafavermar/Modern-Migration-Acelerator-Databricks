# Phase 2: semantic_legacy_search

`semantic_legacy_search` is a future extension. It is not a runtime dependency for the MVP and the MVP bundle must not create Vector Search endpoints or indexes.

## Purpose

- Build embeddings over legacy documentation, ADF exports, Synapse notebooks, SQL scripts and generated blueprints.
- Create a Databricks Vector Search index.
- Support semantic search over the legacy estate.
- Support future RAG use cases such as "ask your legacy platform".
- Improve mapping between legacy assets and recommended Databricks target patterns.

## MVP boundary

The MVP should only produce clean Delta tables and blueprints that a later semantic layer can index. Do not add embedding models, Vector Search endpoints, index creation or RAG runtime code in the MVP.

## Activation criteria

Start this phase only when:

- MVP Delta outputs are trusted.
- Customer approval exists to index legacy artifacts.
- Sensitive content handling is agreed.
- A target user workflow exists, such as migration analyst search or blueprint Q&A.
- Databricks workspace supports the required Vector Search and model capabilities.

## Future inputs

- `bronze.raw_metadata`
- `silver.assets`
- `silver.dependencies`
- `gold.target_databricks_blueprint`
- `gold.risk_register`
- `gold.data_quality_plan`
- External legacy documentation and notebooks

## Future outputs

- Chunked legacy artifact Delta table.
- Embedding-ready document view.
- Vector Search index.
- Search API or notebook utility.
- Optional RAG prompt template for "ask your legacy platform".

## Candidate architecture

1. Read raw metadata, SQL scripts, notebooks and documents.
2. Split content into chunks with stable `chunk_id`.
3. Attach asset lineage: `asset_id`, source system, path, type and risk.
4. Generate embeddings using an approved embedding model.
5. Create or sync a Databricks Vector Search index.
6. Expose semantic search results with links back to Delta assets and blueprints.

## Stoppers

Do not implement if:

- The customer forbids indexing source code or documentation.
- The metadata is too incomplete to produce useful search results.
- Existing enterprise search already covers legacy artifacts and can export results.
- There is no user workflow beyond "it would be nice to search".

## Success criteria

- Analysts can find related pipelines, notebooks, SQL scripts and target patterns by business language.
- Search results link back to source artifacts and generated blueprint rows.
- Index refresh is repeatable.
- No secrets or prohibited content are indexed.
