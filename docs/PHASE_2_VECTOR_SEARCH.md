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

## Future inputs

- `bronze.raw_metadata`
- `silver.assets`
- `silver.dependencies`
- `gold.target_databricks_blueprint`
- External legacy documentation and notebooks

## Future output

A searchable semantic index that links legacy artifacts to target Databricks patterns, migration risks and blueprint recommendations.
