# Phase 2: MLflow Observability

MLflow is a future extension. It is not a mandatory dependency for the MVP.

## MVP observability

The MVP uses Delta control and gold tables:

- `control.run_log`
- `control.metadata_snapshots`
- `gold.risk_register`
- `gold.target_databricks_blueprint`
- `gold.data_quality_plan`

Lakeflow Job run history provides operational execution logs for the Databricks jobs.

## Add MLflow when needed

Add MLflow only if the accelerator introduces:

- LLM-assisted parsing.
- GenAI-based blueprint generation.
- Prompt evaluation.
- Model or agent evaluation.
- GenAI tracing.

## Future design notes

If MLflow is added later, keep deterministic table outputs as the source of truth and use MLflow for experiment, prompt, trace or evaluation metadata. Do not make migration blueprint generation depend on MLflow unless a GenAI component is introduced.
