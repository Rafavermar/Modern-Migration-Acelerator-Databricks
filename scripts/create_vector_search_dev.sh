#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
. "$script_dir/lib/load_env.sh"
load_dotenv ".env"
export MSYS_NO_PATHCONV=1
export MSYS2_ARG_CONV_EXCL="*"

catalog="${DATABRICKS_CATALOG:-migration_accelerator_dev}"
endpoint="${DATABRICKS_VECTOR_SEARCH_ENDPOINT:-mma-vector-search-dev}"
endpoint_type="${DATABRICKS_VECTOR_SEARCH_ENDPOINT_TYPE:-STANDARD}"
index_name="${DATABRICKS_VECTOR_SEARCH_INDEX:-${catalog}.gold.semantic_legacy_documents_vs}"
source_table="${DATABRICKS_VECTOR_SEARCH_SOURCE_TABLE:-${catalog}.gold.semantic_legacy_documents}"
embedding_endpoint="${DATABRICKS_EMBEDDING_MODEL_ENDPOINT:-databricks-qwen3-embedding-0-6b}"

databricks_cmd=(databricks)
if [ -n "${DATABRICKS_PROFILE:-}" ]; then
  databricks_cmd+=(--profile "$DATABRICKS_PROFILE")
fi

wait_index_ready() {
  local max_attempts="${1:-60}"
  local sleep_seconds="${2:-20}"
  local status_file
  status_file="$(mktemp)"

  for attempt in $(seq 1 "$max_attempts"); do
    if "${databricks_cmd[@]}" vector-search-indexes get-index "$index_name" -o json >"$status_file" 2>/dev/null; then
      if python - "$status_file" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
raise SystemExit(0 if payload.get("status", {}).get("ready") is True else 1)
PY
      then
        echo "Vector Search index is ready: $index_name"
        rm -f "$status_file"
        return 0
      fi
      message="$(python - "$status_file" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
print(payload.get("status", {}).get("message", "status unavailable"))
PY
)"
    else
      message="status unavailable"
    fi

    echo "Waiting for Vector Search index readiness ($attempt/$max_attempts): $message"
    sleep "$sleep_seconds"
  done

  rm -f "$status_file"
  echo "Vector Search index did not become ready in time: $index_name" >&2
  return 1
}

echo "Vector Search endpoint: $endpoint ($endpoint_type)"
if "${databricks_cmd[@]}" vector-search-endpoints get-endpoint "$endpoint" >/dev/null 2>&1; then
  echo "Endpoint already exists."
else
  "${databricks_cmd[@]}" vector-search-endpoints create-endpoint "$endpoint" "$endpoint_type" --timeout 30m
fi

if "${databricks_cmd[@]}" vector-search-indexes get-index "$index_name" >/dev/null 2>&1; then
  echo "Index already exists: $index_name"
else
  body_file="$(mktemp)"
  python - "$body_file" "$source_table" "$embedding_endpoint" "$index_name" "$endpoint" <<'PY'
import json
import sys
from pathlib import Path

body_path = Path(sys.argv[1])
source_table = sys.argv[2]
embedding_endpoint = sys.argv[3]
body = {
    "name": f"{source_table.rsplit('.', 1)[0]}.semantic_legacy_documents_vs",
    "delta_sync_index_spec": {
        "source_table": source_table,
        "pipeline_type": "TRIGGERED",
        "embedding_source_columns": [
            {
                "name": "chunk_text",
                "embedding_model_endpoint_name": embedding_endpoint,
            }
        ],
        "columns_to_sync": [
            "chunk_id",
            "run_id",
            "document_type",
            "source_path",
            "source_format",
            "asset_id",
            "asset_name",
            "asset_type",
            "source_system",
            "target_pattern",
            "risk_level",
            "review_priority",
            "chunk_text",
            "content_hash",
            "generated_at",
        ],
    }
}
body["name"] = sys.argv[4]
body["endpoint_name"] = sys.argv[5]
body["primary_key"] = "chunk_id"
body["index_type"] = "DELTA_SYNC"
body["index_subtype"] = "HYBRID"
body_path.write_text(json.dumps(body, indent=2), encoding="utf-8")
PY

  "${databricks_cmd[@]}" vector-search-indexes create-index --json "@$body_file"
  rm -f "$body_file"
fi

wait_index_ready

echo "Triggering index sync: $index_name"
"${databricks_cmd[@]}" vector-search-indexes sync-index "$index_name"

wait_index_ready

echo "Vector Search index status:"
"${databricks_cmd[@]}" vector-search-indexes get-index "$index_name" -o json
