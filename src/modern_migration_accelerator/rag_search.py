from __future__ import annotations

import argparse
import json
import os
import subprocess
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
    log_mlflow: bool


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


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
            "mode": "deterministic_retrieval_brief",
            "llm_endpoint": None,
            "note": "This starter utility retrieves and summarizes evidence without calling an LLM.",
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


def log_to_mlflow(
    *,
    config: SearchConfig,
    row_count: int,
    results_path: Path,
    brief_path: Path,
    trace_path: Path,
) -> None:
    try:
        import mlflow
    except ImportError as exc:
        raise RuntimeError(
            "MLflow logging requested but mlflow is not installed. "
            "Install with: pip install -e .[genai]"
        ) from exc

    if config.experiment_name:
        mlflow.set_experiment(config.experiment_name)

    with mlflow.start_run(run_name="mma-rag-search-dev"):
        mlflow.log_param("index_name", config.index_name)
        mlflow.log_param("query_type", config.query_type.upper())
        mlflow.log_param("question", config.query_text[:500])
        mlflow.log_metric("retrieved_chunks", row_count)
        mlflow.log_artifact(str(results_path), artifact_path="rag_search")
        mlflow.log_artifact(str(brief_path), artifact_path="rag_search")
        mlflow.log_artifact(str(trace_path), artifact_path="rag_search")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Query the dev Vector Search index and build a RAG-ready retrieval brief.")
    parser.add_argument("question", nargs="?", default="Which high risk legacy assets should be migrated first?")
    parser.add_argument("--num-results", type=int, default=int(os.environ.get("VECTOR_SEARCH_NUM_RESULTS", "5")))
    parser.add_argument("--query-type", default=os.environ.get("VECTOR_SEARCH_QUERY_TYPE", "HYBRID"))
    parser.add_argument("--index-name", default="")
    parser.add_argument("--profile", default="")
    parser.add_argument("--output-dir", default=os.environ.get("RAG_OUTPUT_DIR", "local_outputs/rag"))
    parser.add_argument("--log-mlflow", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
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
        log_mlflow=args.log_mlflow,
    )

    response = query_vector_search(config)
    rows = parse_vector_search_rows(response)
    brief = build_retrieval_brief(config.query_text, rows)
    results_path, brief_path, trace_path = write_outputs(config, response, rows, brief)

    if config.log_mlflow:
        log_to_mlflow(
            config=config,
            row_count=len(rows),
            results_path=results_path,
            brief_path=brief_path,
            trace_path=trace_path,
        )

    print(brief)
    print(f"Search JSON: {results_path}")
    print(f"Brief Markdown: {brief_path}")
    print(f"Trace JSON: {trace_path}")
    if config.log_mlflow:
        print(f"MLflow experiment: {config.experiment_name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
