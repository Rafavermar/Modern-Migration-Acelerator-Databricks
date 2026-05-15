#!/usr/bin/env bash
set -euo pipefail

if [ -f .env ]; then
  set -a
  . ./.env
  set +a
fi

target="${DATABRICKS_BUNDLE_ENV:-dev}"

if [ -n "${DATABRICKS_CATALOG:-}" ]; then export BUNDLE_VAR_catalog="$DATABRICKS_CATALOG"; fi
if [ -n "${DATABRICKS_SPARK_VERSION:-}" ]; then export BUNDLE_VAR_spark_version="$DATABRICKS_SPARK_VERSION"; fi
if [ -n "${DATABRICKS_NODE_TYPE_ID:-}" ]; then export BUNDLE_VAR_node_type_id="$DATABRICKS_NODE_TYPE_ID"; fi

databricks_cmd=(databricks)
if [ -n "${DATABRICKS_PROFILE:-}" ]; then
  databricks_cmd+=(--profile "$DATABRICKS_PROFILE")
fi

"${databricks_cmd[@]}" bundle run target_demo -t "$target"
