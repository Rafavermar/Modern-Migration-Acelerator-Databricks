#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
. "$script_dir/lib/load_env.sh"
load_dotenv ".env"
export MSYS_NO_PATHCONV=1
export MSYS2_ARG_CONV_EXCL="*"

catalog="${DATABRICKS_CATALOG:-migration_accelerator_dev}"
index_name="${DATABRICKS_VECTOR_SEARCH_INDEX:-${catalog}.gold.semantic_legacy_documents_vs}"
query_text="${1:-Which high risk legacy assets should be migrated first?}"
num_results="${VECTOR_SEARCH_NUM_RESULTS:-5}"

databricks_cmd=(databricks)
if [ -n "${DATABRICKS_PROFILE:-}" ]; then
  databricks_cmd+=(--profile "$DATABRICKS_PROFILE")
fi

body_file="$(mktemp)"
python - "$body_file" "$query_text" "$num_results" <<'PY'
import json
import sys
from pathlib import Path

body_path = Path(sys.argv[1])
query_text = sys.argv[2]
num_results = int(sys.argv[3])
body = {
    "query_text": query_text,
    "query_type": "HYBRID",
    "num_results": num_results,
    "columns": [
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
    ],
}
body_path.write_text(json.dumps(body, indent=2), encoding="utf-8")
PY

"${databricks_cmd[@]}" api post "/api/2.0/vector-search/indexes/${index_name}/query" --json "@$body_file" -o json
rm -f "$body_file"
