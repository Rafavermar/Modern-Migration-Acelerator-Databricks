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

## Activation criteria

Start this phase only when:

- A GenAI or LLM-assisted feature exists.
- Prompts or generated outputs affect migration recommendations.
- The team needs traceability, evaluation or regression testing for model behavior.
- A reviewer has defined acceptance criteria for generated recommendations.

## Future design notes

If MLflow is added later, keep deterministic table outputs as the source of truth and use MLflow for experiment, prompt, trace or evaluation metadata. Do not make migration blueprint generation depend on MLflow unless a GenAI component is introduced.

## Future tracked artifacts

- Prompt versions.
- Retrieval context.
- Generated blueprint suggestions.
- Human review outcomes.
- Evaluation datasets.
- Trace spans for RAG and agent workflows.
- Quality metrics such as groundedness, correctness and completeness.

## Stoppers

Do not implement if:

- The accelerator remains deterministic.
- Recommendations are generated only by rules and Delta transforms.
- The customer has no process for reviewing GenAI outputs.
- The customer cannot approve storage of prompts, traces or retrieved context.

## Success criteria

- Every GenAI recommendation can be traced to prompt, retrieval context and model.
- Evaluation runs can compare prompt or model versions.
- Failed or low-confidence outputs are visible before customer delivery.
- Deterministic Delta outputs remain the official source of truth.
