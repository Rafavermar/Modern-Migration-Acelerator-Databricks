from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_COLUMNS = [
    "chunk_id",
    "document_type",
    "asset_name",
    "asset_type",
    "source_system",
    "risk_level",
    "review_priority",
    "target_pattern",
    "source_path",
    "chunk_text",
]


@dataclass(frozen=True)
class SearchConfig:
    index_name: str
    query_text: str
    num_results: int
    query_type: str
    profile: str
    output_dir: Path
    experiment_name: str
    mlflow_tracking_uri: str
    llm_endpoint: str
    generate_answer: bool
    max_tokens: int
    temperature: float
    log_mlflow: bool


@dataclass(frozen=True)
class WorkflowOutputs:
    response: dict[str, Any]
    rows: list[dict[str, Any]]
    brief: str
    results_path: Path
    brief_path: Path
    trace_path: Path
    generation_response: dict[str, Any] | None = None
    generated_answer: str = ""
    generated_answer_path: Path | None = None
    generation_path: Path | None = None


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def configure_console_encoding() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def load_dotenv(path: Path) -> None:
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def default_index_name() -> str:
    catalog = os.environ.get("DATABRICKS_CATALOG", "migration_accelerator_dev")
    return os.environ.get(
        "DATABRICKS_VECTOR_SEARCH_INDEX",
        f"{catalog}.gold.semantic_legacy_documents_vs",
    )


def default_mlflow_tracking_uri(profile: str) -> str:
    explicit_uri = os.environ.get("MLFLOW_TRACKING_URI", "").strip()
    if explicit_uri:
        return explicit_uri
    if profile:
        return f"databricks://{profile}"
    return "databricks"


def default_llm_endpoint() -> str:
    return os.environ.get("DATABRICKS_LLM_ENDPOINT", "databricks-gemma-3-12b").strip()


def databricks_command(profile: str) -> list[str]:
    command = ["databricks"]
    if profile:
        command.extend(["--profile", profile])
    return command


def query_vector_search(config: SearchConfig) -> dict[str, Any]:
    payload = {
        "query_text": config.query_text,
        "query_type": config.query_type.upper(),
        "num_results": config.num_results,
        "columns": DEFAULT_COLUMNS,
    }

    with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".json", delete=False) as handle:
        json.dump(payload, handle, indent=2)
        body_path = Path(handle.name)

    try:
        command = databricks_command(config.profile)
        command.extend(
            [
                "api",
                "post",
                f"/api/2.0/vector-search/indexes/{config.index_name}/query",
                "--json",
                f"@{body_path}",
                "-o",
                "json",
            ]
        )
        result = subprocess.run(command, check=True, capture_output=True, text=True)
    finally:
        body_path.unlink(missing_ok=True)

    return json.loads(result.stdout)


def invoke_chat_endpoint(config: SearchConfig, messages: list[dict[str, str]]) -> dict[str, Any]:
    if not config.llm_endpoint:
        raise ValueError("DATABRICKS_LLM_ENDPOINT is required when --generate-answer is used.")

    payload = {
        "messages": messages,
        "temperature": config.temperature,
        "max_tokens": config.max_tokens,
        "stream": False,
    }

    with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".json", delete=False) as handle:
        json.dump(payload, handle, indent=2)
        body_path = Path(handle.name)

    try:
        command = databricks_command(config.profile)
        command.extend(
            [
                "serving-endpoints",
                "query",
                config.llm_endpoint,
                "--json",
                f"@{body_path}",
                "-o",
                "json",
            ]
        )
        result = subprocess.run(command, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as exc:
        message = exc.stderr.strip() or exc.stdout.strip() or str(exc)
        raise RuntimeError(f"Databricks LLM endpoint query failed: {message}") from exc
    finally:
        body_path.unlink(missing_ok=True)

    return json.loads(result.stdout)


def parse_vector_search_rows(response: dict[str, Any]) -> list[dict[str, Any]]:
    columns = [column.get("name", "") for column in response.get("manifest", {}).get("columns", [])]
    data_array = response.get("result", {}).get("data_array", [])

    rows: list[dict[str, Any]] = []
    for raw_row in data_array:
        row = {name: raw_row[index] for index, name in enumerate(columns) if name}
        if len(raw_row) > len(columns):
            for offset, value in enumerate(raw_row[len(columns) :], start=1):
                row[f"extra_{offset}"] = value
        rows.append(row)
    return rows


def compact_text(value: Any, max_chars: int = 700) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= max_chars:
        return text
    return f"{text[: max_chars - 3].rstrip()}..."


def display_value(row: dict[str, Any], name: str, fallback: str = "unknown") -> str:
    value = row.get(name)
    if value is None or str(value).strip() == "":
        return fallback
    return str(value)


def inline_code(value: str) -> str:
    return f"`{value.replace('`', '')}`"


def evidence_block(rows: list[dict[str, Any]], max_rows: int = 5, max_chars: int = 900) -> str:
    blocks: list[str] = []
    for index, row in enumerate(rows[:max_rows], start=1):
        blocks.append(
            "\n".join(
                [
                    f"Evidence {index}",
                    f"asset_name: {display_value(row, 'asset_name')}",
                    f"document_type: {display_value(row, 'document_type')}",
                    f"risk_level: {display_value(row, 'risk_level')}",
                    f"review_priority: {display_value(row, 'review_priority')}",
                    f"target_pattern: {display_value(row, 'target_pattern')}",
                    f"source_path: {display_value(row, 'source_path')}",
                    f"chunk_text: {compact_text(row.get('chunk_text'), max_chars=max_chars)}",
                ]
            )
        )
    return "\n\n".join(blocks)


def build_llm_messages(question: str, rows: list[dict[str, Any]]) -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "content": (
                "You are a migration assessment assistant for Databricks modernization. "
                "Use only the evidence provided. Be concise. If evidence is incomplete, say what must be checked next. "
                "Do not invent systems, dependencies, risk levels or target patterns. "
                "For first-review recommendations, prioritize p1 assets, high-risk assets, or assets with explicit blocking data quality errors. "
                "Never recommend a p3 or low-risk asset as the first review target solely because it is the only row with a populated priority."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Question:\n{question}\n\n"
                f"Retrieved migration evidence:\n{evidence_block(rows)}\n\n"
                "Write a grounded answer with three sections: Answer, Evidence, Next checks. "
                "If the retrieved evidence does not contain p1 or high-risk assets, say that the first-review candidate is not proven by the retrieved evidence and recommend checking the priority matrix and risk register."
            ),
        },
    ]


def extract_chat_content(response: dict[str, Any]) -> str:
    choices = response.get("choices")
    if isinstance(choices, list) and choices:
        message = choices[0].get("message") if isinstance(choices[0], dict) else None
        if isinstance(message, dict) and message.get("content"):
            return str(message["content"])
        if isinstance(choices[0], dict) and choices[0].get("text"):
            return str(choices[0]["text"])

    predictions = response.get("predictions")
    if isinstance(predictions, list) and predictions:
        first = predictions[0]
        if isinstance(first, dict):
            return str(first.get("content") or first.get("text") or first)
        return str(first)

    if response.get("output_text"):
        return str(response["output_text"])
    return json.dumps(response, indent=2)


def build_retrieval_brief(question: str, rows: list[dict[str, Any]]) -> str:
    generated_at = utc_timestamp()
    lines = [
        "# Migration Retrieval Brief",
        "",
        f"Generated at: `{generated_at}`",
        f"Question: {question}",
        "",
    ]

    if not rows:
        lines.extend(
            [
                "## Short Answer",
                "",
                "No matching migration evidence was returned by Vector Search.",
                "",
                "## Next Checks",
                "",
                "- Confirm the Vector Search index is synced.",
                "- Re-run the semantic index prep job after new metadata is loaded.",
                "- Try a more specific question with source system, asset name or target pattern.",
            ]
        )
        return "\n".join(lines) + "\n"

    p1_assets = sorted(
        {
            display_value(row, "asset_name")
            for row in rows
            if display_value(row, "review_priority", "").lower() == "p1"
        }
    )
    high_risk_assets = sorted(
        {
            display_value(row, "asset_name")
            for row in rows
            if display_value(row, "risk_level", "").lower() == "high"
        }
    )
    named_assets = sorted({display_value(row, "asset_name") for row in rows})

    focus_assets = p1_assets or high_risk_assets or named_assets[:3]
    focus_text = ", ".join(focus_assets[:5])
    lines.extend(
        [
            "## Short Answer",
            "",
            f"The strongest retrieved evidence points to {inline_code(focus_text)}. "
            "Treat this as a grounded search brief, not an autonomous migration decision.",
            "",
            "## Evidence",
            "",
        ]
    )

    for index, row in enumerate(rows, start=1):
        asset = display_value(row, "asset_name")
        document_type = display_value(row, "document_type")
        risk = display_value(row, "risk_level")
        priority = display_value(row, "review_priority")
        target = display_value(row, "target_pattern")
        source = display_value(row, "source_path")
        chunk = compact_text(row.get("chunk_text"))
        lines.extend(
            [
                f"{index}. {inline_code(asset)}",
                f"   Evidence type: {inline_code(document_type)} | risk: {inline_code(risk)} | priority: {inline_code(priority)} | target: {inline_code(target)}",
                f"   Source: {inline_code(source)}",
                f"   Snippet: {chunk}",
                "",
            ]
        )

    lines.extend(
        [
            "## Next Checks",
            "",
            "- Validate priority in `gold.asset_priority_matrix`.",
            "- Validate risk detail in `gold.risk_register`.",
            "- Check graph impact in Neo4j or `gold.graph_edges`.",
            "- Confirm target decisions in `gold.target_databricks_blueprint` before implementation.",
        ]
    )
    return "\n".join(lines) + "\n"


def build_generated_answer_markdown(
    *,
    question: str,
    generated_answer: str,
    llm_endpoint: str,
    rows: list[dict[str, Any]],
) -> str:
    evidence_refs = [
        f"- `{display_value(row, 'asset_name')}` from `{display_value(row, 'source_path')}`"
        for row in rows[:5]
    ]
    return "\n".join(
        [
            "# Migration RAG Answer",
            "",
            f"Generated at: `{utc_timestamp()}`",
            f"Question: {question}",
            f"LLM endpoint: `{llm_endpoint}`",
            "",
            "## Generated Answer",
            "",
            generated_answer.strip(),
            "",
            "## Evidence References",
            "",
            *(evidence_refs or ["- No retrieved evidence."]),
            "",
            "## Guardrail",
            "",
            "This answer is grounded in retrieved evidence and must be reviewed against Delta outputs before migration execution.",
            "",
        ]
    )


def build_trace_payload(config: SearchConfig, response: dict[str, Any], rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema": "modern_migration_accelerator.rag_trace.v1",
        "generated_at": utc_timestamp(),
        "question": config.query_text,
        "retrieval": {
            "index_name": config.index_name,
            "query_type": config.query_type.upper(),
            "num_results_requested": config.num_results,
            "num_results_returned": len(rows),
            "row_count": response.get("result", {}).get("row_count", len(rows)),
            "next_page_token_present": bool(response.get("next_page_token")),
        },
        "generation": {
            "mode": "llm_grounded_answer" if config.generate_answer else "deterministic_retrieval_brief",
            "llm_endpoint": config.llm_endpoint if config.generate_answer else None,
            "note": (
                "This workflow called a Databricks Model Serving chat endpoint."
                if config.generate_answer
                else "This starter utility retrieves and summarizes evidence without calling an LLM."
            ),
        },
        "evaluation_ready": {
            "human_review_status": "pending",
            "expected_answer": None,
            "recommended_scorers": ["relevance_to_query", "groundedness", "safety"],
        },
        "result_refs": [
            {
                "chunk_id": row.get("chunk_id"),
                "asset_name": row.get("asset_name"),
                "document_type": row.get("document_type"),
                "risk_level": row.get("risk_level"),
                "review_priority": row.get("review_priority"),
                "target_pattern": row.get("target_pattern"),
                "source_path": row.get("source_path"),
            }
            for row in rows
        ],
    }


def write_outputs(
    config: SearchConfig,
    response: dict[str, Any],
    rows: list[dict[str, Any]],
    brief: str,
) -> tuple[Path, Path, Path]:
    config.output_dir.mkdir(parents=True, exist_ok=True)
    results_path = config.output_dir / "latest_search.json"
    brief_path = config.output_dir / "latest_answer.md"
    trace_path = config.output_dir / "latest_trace.json"

    results_payload = {
        "question": config.query_text,
        "index_name": config.index_name,
        "query_type": config.query_type.upper(),
        "rows": rows,
        "raw_response": response,
    }
    results_path.write_text(json.dumps(results_payload, indent=2), encoding="utf-8")
    brief_path.write_text(brief, encoding="utf-8")
    trace_path.write_text(
        json.dumps(build_trace_payload(config, response, rows), indent=2),
        encoding="utf-8",
    )
    return results_path, brief_path, trace_path


def write_generation_outputs(
    config: SearchConfig,
    generation_response: dict[str, Any],
    generated_answer: str,
    rows: list[dict[str, Any]],
) -> tuple[Path, Path]:
    config.output_dir.mkdir(parents=True, exist_ok=True)
    generation_path = config.output_dir / "latest_generation.json"
    answer_path = config.output_dir / "latest_llm_answer.md"

    generation_path.write_text(
        json.dumps(
            {
                "question": config.query_text,
                "llm_endpoint": config.llm_endpoint,
                "generated_answer": generated_answer,
                "raw_response": generation_response,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    answer_path.write_text(
        build_generated_answer_markdown(
            question=config.query_text,
            generated_answer=generated_answer,
            llm_endpoint=config.llm_endpoint,
            rows=rows,
        ),
        encoding="utf-8",
    )
    return generation_path, answer_path


def log_to_mlflow(
    *,
    config: SearchConfig,
    outputs: WorkflowOutputs,
) -> None:
    try:
        import mlflow
    except ImportError as exc:
        raise RuntimeError(
            "MLflow logging requested but mlflow is not installed. "
            "Install with: pip install -e .[genai]"
        ) from exc

    mlflow.set_tracking_uri(config.mlflow_tracking_uri)
    if config.experiment_name:
        mlflow.set_experiment(config.experiment_name)

    with mlflow.start_run(run_name="mma-rag-search-dev"):
        mlflow.log_param("index_name", config.index_name)
        mlflow.log_param("query_type", config.query_type.upper())
        mlflow.log_param("question", config.query_text[:500])
        mlflow.log_param("generate_answer", config.generate_answer)
        if config.generate_answer:
            mlflow.log_param("llm_endpoint", config.llm_endpoint)
            mlflow.log_metric("generated_answer_chars", len(outputs.generated_answer))
        mlflow.log_metric("retrieved_chunks", len(outputs.rows))
        mlflow.log_artifact(str(outputs.results_path), artifact_path="rag_search")
        mlflow.log_artifact(str(outputs.brief_path), artifact_path="rag_search")
        mlflow.log_artifact(str(outputs.trace_path), artifact_path="rag_search")
        if outputs.generation_path and outputs.generated_answer_path:
            mlflow.log_artifact(str(outputs.generation_path), artifact_path="rag_search")
            mlflow.log_artifact(str(outputs.generated_answer_path), artifact_path="rag_search")


def run_workflow(config: SearchConfig, *, trace_mlflow: bool = False) -> WorkflowOutputs:
    query_fn = query_vector_search
    generate_fn = invoke_chat_endpoint

    if trace_mlflow:
        import mlflow

        query_fn = mlflow.trace(
            name="vector_search_retrieval",
            span_type="RETRIEVER",
            attributes={"index_name": config.index_name, "query_type": config.query_type.upper()},
        )(query_vector_search)
        generate_fn = mlflow.trace(
            name="databricks_llm_answer",
            span_type="LLM",
            attributes={"llm_endpoint": config.llm_endpoint},
        )(invoke_chat_endpoint)

    response = query_fn(config)
    rows = parse_vector_search_rows(response)
    brief = build_retrieval_brief(config.query_text, rows)
    results_path, brief_path, trace_path = write_outputs(config, response, rows, brief)

    generation_response = None
    generated_answer = ""
    generation_path = None
    generated_answer_path = None
    if config.generate_answer:
        messages = build_llm_messages(config.query_text, rows)
        generation_response = generate_fn(config, messages)
        generated_answer = extract_chat_content(generation_response)
        generation_path, generated_answer_path = write_generation_outputs(
            config,
            generation_response,
            generated_answer,
            rows,
        )

    return WorkflowOutputs(
        response=response,
        rows=rows,
        brief=brief,
        results_path=results_path,
        brief_path=brief_path,
        trace_path=trace_path,
        generation_response=generation_response,
        generated_answer=generated_answer,
        generated_answer_path=generated_answer_path,
        generation_path=generation_path,
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Query the dev Vector Search index and build a RAG-ready retrieval brief.")
    parser.add_argument("question", nargs="?", default="Which high risk legacy assets should be migrated first?")
    parser.add_argument("--num-results", type=int, default=int(os.environ.get("VECTOR_SEARCH_NUM_RESULTS", "5")))
    parser.add_argument("--query-type", default=os.environ.get("VECTOR_SEARCH_QUERY_TYPE", "HYBRID"))
    parser.add_argument("--index-name", default="")
    parser.add_argument("--profile", default="")
    parser.add_argument("--output-dir", default=os.environ.get("RAG_OUTPUT_DIR", "local_outputs/rag"))
    parser.add_argument("--generate-answer", action="store_true")
    parser.add_argument("--llm-endpoint", default="")
    parser.add_argument("--max-tokens", type=int, default=int(os.environ.get("RAG_LLM_MAX_TOKENS", "700")))
    parser.add_argument("--temperature", type=float, default=float(os.environ.get("RAG_LLM_TEMPERATURE", "0.0")))
    parser.add_argument("--log-mlflow", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    configure_console_encoding()
    load_dotenv(Path(".env"))
    args = parse_args(argv)
    profile = args.profile or os.environ.get("DATABRICKS_PROFILE", "")
    experiment_name = os.environ.get("MLFLOW_EXPERIMENT_NAME", "/Shared/modern-migration-accelerator")
    config = SearchConfig(
        index_name=args.index_name or default_index_name(),
        query_text=args.question,
        num_results=args.num_results,
        query_type=args.query_type,
        profile=profile,
        output_dir=Path(args.output_dir),
        experiment_name=experiment_name,
        mlflow_tracking_uri=default_mlflow_tracking_uri(profile),
        llm_endpoint=args.llm_endpoint or default_llm_endpoint(),
        generate_answer=args.generate_answer,
        max_tokens=args.max_tokens,
        temperature=args.temperature,
        log_mlflow=args.log_mlflow,
    )

    if config.log_mlflow:
        import mlflow

        mlflow.set_tracking_uri(config.mlflow_tracking_uri)
        if config.experiment_name:
            mlflow.set_experiment(config.experiment_name)

    outputs = run_workflow(config, trace_mlflow=config.log_mlflow)

    if config.log_mlflow:
        log_to_mlflow(config=config, outputs=outputs)

    print(outputs.brief)
    if outputs.generated_answer:
        print("## Generated RAG Answer")
        print()
        print(outputs.generated_answer)
        print()
    print(f"Search JSON: {outputs.results_path}")
    print(f"Brief Markdown: {outputs.brief_path}")
    print(f"Trace JSON: {outputs.trace_path}")
    if outputs.generation_path and outputs.generated_answer_path:
        print(f"Generation JSON: {outputs.generation_path}")
        print(f"LLM Answer Markdown: {outputs.generated_answer_path}")
    if config.log_mlflow:
        print(f"MLflow experiment: {config.experiment_name}")
        print(f"MLflow tracking URI: {config.mlflow_tracking_uri}")
    if config.generate_answer:
        print(f"LLM endpoint: {config.llm_endpoint}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
