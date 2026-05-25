from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from modern_migration_accelerator.rag_search import (
    SearchConfig,
    WorkflowOutputs,
    configure_console_encoding,
    default_index_name,
    default_llm_endpoint,
    default_mlflow_tracking_uri,
    load_dotenv,
    run_workflow,
    utc_timestamp,
)


@dataclass(frozen=True)
class EvalCase:
    case_id: str
    question: str
    expected_terms: list[str]
    expected_assets: list[str]
    min_score: float


@dataclass(frozen=True)
class EvalResult:
    case: EvalCase
    score: float
    passed: bool
    matched_terms: list[str]
    missing_terms: list[str]
    matched_assets: list[str]
    missing_assets: list[str]
    retrieved_chunks: int
    output_dir: Path


def normalize_text(value: Any) -> str:
    return " ".join(str(value or "").lower().split())


def load_eval_cases(path: Path) -> list[EvalCase]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    cases = payload.get("cases", payload if isinstance(payload, list) else [])
    if not isinstance(cases, list):
        raise ValueError(f"Invalid RAG eval case file: {path}")

    loaded: list[EvalCase] = []
    for item in cases:
        loaded.append(
            EvalCase(
                case_id=str(item["id"]),
                question=str(item["question"]),
                expected_terms=[str(value) for value in item.get("expected_terms", [])],
                expected_assets=[str(value) for value in item.get("expected_assets", [])],
                min_score=float(item.get("min_score", 0.6)),
            )
        )
    return loaded


def evaluate_case(case: EvalCase, outputs: WorkflowOutputs) -> EvalResult:
    rows_json = json.dumps(outputs.rows, ensure_ascii=False)
    scored_text = normalize_text(f"{outputs.brief}\n{outputs.generated_answer}\n{rows_json}")

    matched_terms = [term for term in case.expected_terms if normalize_text(term) in scored_text]
    missing_terms = [term for term in case.expected_terms if term not in matched_terms]
    matched_assets = [asset for asset in case.expected_assets if normalize_text(asset) in scored_text]
    missing_assets = [asset for asset in case.expected_assets if asset not in matched_assets]

    expected_total = len(case.expected_terms) + len(case.expected_assets)
    if expected_total == 0:
        score = 1.0 if outputs.rows else 0.0
    else:
        score = (len(matched_terms) + len(matched_assets)) / expected_total

    return EvalResult(
        case=case,
        score=round(score, 4),
        passed=score >= case.min_score,
        matched_terms=matched_terms,
        missing_terms=missing_terms,
        matched_assets=matched_assets,
        missing_assets=missing_assets,
        retrieved_chunks=len(outputs.rows),
        output_dir=outputs.results_path.parent,
    )


def result_to_dict(result: EvalResult) -> dict[str, Any]:
    return {
        "id": result.case.case_id,
        "question": result.case.question,
        "score": result.score,
        "min_score": result.case.min_score,
        "passed": result.passed,
        "retrieved_chunks": result.retrieved_chunks,
        "matched_terms": result.matched_terms,
        "missing_terms": result.missing_terms,
        "matched_assets": result.matched_assets,
        "missing_assets": result.missing_assets,
        "output_dir": str(result.output_dir),
    }


def build_summary_markdown(results: list[EvalResult], *, generated_at: str, generate_answer: bool) -> str:
    passed = sum(1 for result in results if result.passed)
    lines = [
        "# RAG Evaluation Summary",
        "",
        f"Generated at: `{generated_at}`",
        f"Mode: `{'retrieval_plus_generation' if generate_answer else 'retrieval_only'}`",
        f"Passed: `{passed}/{len(results)}`",
        "",
        "| Case | Score | Pass | Retrieved | Missing |",
        "| --- | ---: | --- | ---: | --- |",
    ]
    for result in results:
        missing = result.missing_terms + result.missing_assets
        lines.append(
            "| "
            + " | ".join(
                [
                    f"`{result.case.case_id}`",
                    f"{result.score:.2f}",
                    "yes" if result.passed else "no",
                    str(result.retrieved_chunks),
                    ", ".join(missing) if missing else "-",
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- This is a lightweight regression check, not a final GenAI judge.",
            "- A failed case means retrieval, metadata coverage or prompt grounding needs review.",
            "- Generated answers remain advisory and must be checked against Delta gold outputs and Neo4j.",
            "",
        ]
    )
    return "\n".join(lines)


def log_eval_to_mlflow(
    *,
    experiment_name: str,
    tracking_uri: str,
    generate_answer: bool,
    summary_path: Path,
    results_path: Path,
    results: list[EvalResult],
) -> None:
    try:
        import mlflow
    except ImportError as exc:
        raise RuntimeError(
            "MLflow logging requested but mlflow is not installed. "
            "Install with: pip install -e .[genai]"
        ) from exc

    mlflow.set_tracking_uri(tracking_uri)
    if experiment_name:
        mlflow.set_experiment(experiment_name)

    passed = sum(1 for result in results if result.passed)
    with mlflow.start_run(run_name="mma-rag-eval-dev"):
        mlflow.log_param("generate_answer", generate_answer)
        mlflow.log_metric("eval_cases", len(results))
        mlflow.log_metric("eval_passed", passed)
        mlflow.log_metric("eval_pass_rate", passed / len(results) if results else 0.0)
        mlflow.log_artifact(str(summary_path), artifact_path="rag_eval")
        mlflow.log_artifact(str(results_path), artifact_path="rag_eval")


def run_evaluation(
    *,
    cases: list[EvalCase],
    index_name: str,
    profile: str,
    output_dir: Path,
    num_results: int,
    query_type: str,
    generate_answer: bool,
    llm_endpoint: str,
    max_tokens: int,
    temperature: float,
) -> list[EvalResult]:
    results: list[EvalResult] = []
    for case in cases:
        case_output_dir = output_dir / case.case_id
        config = SearchConfig(
            index_name=index_name,
            query_text=case.question,
            num_results=num_results,
            query_type=query_type,
            profile=profile,
            output_dir=case_output_dir,
            experiment_name="",
            mlflow_tracking_uri="",
            llm_endpoint=llm_endpoint,
            generate_answer=generate_answer,
            max_tokens=max_tokens,
            temperature=temperature,
            log_mlflow=False,
        )
        outputs = run_workflow(config)
        results.append(evaluate_case(case, outputs))
    return results


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a small RAG retrieval/generation evaluation set.")
    parser.add_argument("--cases", default="contracts/rag_eval_questions.json")
    parser.add_argument("--output-dir", default=os.environ.get("RAG_EVAL_OUTPUT_DIR", "local_outputs/rag_eval"))
    parser.add_argument("--num-results", type=int, default=int(os.environ.get("VECTOR_SEARCH_NUM_RESULTS", "5")))
    parser.add_argument("--query-type", default=os.environ.get("VECTOR_SEARCH_QUERY_TYPE", "HYBRID"))
    parser.add_argument("--index-name", default="")
    parser.add_argument("--profile", default="")
    parser.add_argument("--generate-answer", action="store_true")
    parser.add_argument("--llm-endpoint", default="")
    parser.add_argument("--max-tokens", type=int, default=int(os.environ.get("RAG_LLM_MAX_TOKENS", "1200")))
    parser.add_argument("--temperature", type=float, default=float(os.environ.get("RAG_LLM_TEMPERATURE", "0.0")))
    parser.add_argument("--log-mlflow", action="store_true")
    parser.add_argument("--fail-on-miss", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    configure_console_encoding()
    load_dotenv(Path(".env"))
    args = parse_args(argv)

    profile = args.profile or os.environ.get("DATABRICKS_PROFILE", "")
    experiment_name = os.environ.get("MLFLOW_EXPERIMENT_NAME", "/Shared/modern-migration-accelerator")
    tracking_uri = default_mlflow_tracking_uri(profile)
    output_dir = Path(args.output_dir)
    generated_at = utc_timestamp()

    results = run_evaluation(
        cases=load_eval_cases(Path(args.cases)),
        index_name=args.index_name or default_index_name(),
        profile=profile,
        output_dir=output_dir,
        num_results=args.num_results,
        query_type=args.query_type,
        generate_answer=args.generate_answer,
        llm_endpoint=args.llm_endpoint or default_llm_endpoint(),
        max_tokens=args.max_tokens,
        temperature=args.temperature,
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    results_path = output_dir / "latest_eval.json"
    summary_path = output_dir / "latest_eval.md"
    results_payload = {
        "schema": "modern_migration_accelerator.rag_eval_results.v1",
        "generated_at": generated_at,
        "generate_answer": args.generate_answer,
        "results": [result_to_dict(result) for result in results],
    }
    results_path.write_text(json.dumps(results_payload, indent=2), encoding="utf-8")
    summary_path.write_text(
        build_summary_markdown(results, generated_at=generated_at, generate_answer=args.generate_answer),
        encoding="utf-8",
    )

    if args.log_mlflow:
        log_eval_to_mlflow(
            experiment_name=experiment_name,
            tracking_uri=tracking_uri,
            generate_answer=args.generate_answer,
            summary_path=summary_path,
            results_path=results_path,
            results=results,
        )

    print(summary_path.read_text(encoding="utf-8"))
    print(f"Eval JSON: {results_path}")
    print(f"Eval Markdown: {summary_path}")
    if args.log_mlflow:
        print(f"MLflow experiment: {experiment_name}")
        print(f"MLflow tracking URI: {tracking_uri}")
    if args.fail_on_miss and not all(result.passed for result in results):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
