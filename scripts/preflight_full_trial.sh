#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
. "$script_dir/lib/load_env.sh"
if [ -f .env ]; then
  load_dotenv ".env"
else
  echo "WARN: .env not found. Copy .env.example to .env before the first Databricks run." >&2
fi

require_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "$1 is required but was not found on PATH." >&2
    exit 1
  fi
  echo "OK: $1 -> $(command -v "$1")"
}

require_command python
require_command git
require_command databricks

if [ -z "${DATABRICKS_CATALOG:-}" ]; then
  echo "DATABRICKS_CATALOG is required." >&2
  exit 1
fi
echo "OK: DATABRICKS_CATALOG=$DATABRICKS_CATALOG"

if [ -z "${DATABRICKS_NODE_TYPE_ID:-}" ]; then
  echo "OK: DATABRICKS_NODE_TYPE_ID is not set. The default bundle jobs use serverless compute."
else
  echo "OK: DATABRICKS_NODE_TYPE_ID=$DATABRICKS_NODE_TYPE_ID"
fi

databricks_cmd=(databricks)
if [ -n "${DATABRICKS_PROFILE:-}" ]; then
  databricks_cmd+=(--profile "$DATABRICKS_PROFILE")
  echo "OK: DATABRICKS_PROFILE=$DATABRICKS_PROFILE"
fi

if [ -n "${DATABRICKS_WORKSPACE_ID:-}" ]; then
  echo "OK: DATABRICKS_WORKSPACE_ID=$DATABRICKS_WORKSPACE_ID"
fi

if ! "${databricks_cmd[@]}" current-user me --output json >/dev/null; then
  echo "Databricks CLI is not authenticated for the configured profile. Run databricks auth login against the Full Trial workspace." >&2
  exit 1
fi
echo "OK: Databricks CLI authentication works."

auth_description="$("${databricks_cmd[@]}" auth describe --output json 2>/dev/null || true)"
if echo "$auth_description" | grep -Eiq 'community|free'; then
  echo "Configured Databricks auth appears to reference Free/Community Edition. Do not deploy. Re-login to the Full Trial workspace." >&2
  exit 1
fi

echo
echo "Preflight passed. Next safe step: bash scripts/validate_bundle.sh"
