#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
. "$script_dir/lib/load_env.sh"
load_dotenv ".env"

target="${DATABRICKS_BUNDLE_ENV:-dev}"

if [ -n "${DATABRICKS_CATALOG:-}" ]; then export BUNDLE_VAR_catalog="$DATABRICKS_CATALOG"; fi
if [ -n "${LEGACY_METADATA_SOURCE_ROOT:-}" ]; then export BUNDLE_VAR_source_root="$LEGACY_METADATA_SOURCE_ROOT"; fi
if [ -n "${DATABRICKS_SPARK_VERSION:-}" ]; then export BUNDLE_VAR_spark_version="$DATABRICKS_SPARK_VERSION"; fi
if [ -n "${DATABRICKS_NODE_TYPE_ID:-}" ]; then export BUNDLE_VAR_node_type_id="$DATABRICKS_NODE_TYPE_ID"; fi

databricks_cmd=(databricks)
if [ -n "${DATABRICKS_PROFILE:-}" ]; then
  databricks_cmd+=(--profile "$DATABRICKS_PROFILE")
fi

"${databricks_cmd[@]}" bundle deploy -t "$target"
