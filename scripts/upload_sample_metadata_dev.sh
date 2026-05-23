#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$script_dir/.." && pwd)"
. "$script_dir/lib/load_env.sh"
load_dotenv "$repo_root/.env"
export MSYS_NO_PATHCONV=1
export MSYS2_ARG_CONV_EXCL="*"
cd "$repo_root"

catalog="${DATABRICKS_CATALOG:-migration_accelerator_dev}"
schema="landing"
volume="legacy_metadata"
sample_source="samples/legacy_metadata"
sample_source_root="/Volumes/${catalog}/${schema}/${volume}/demo"
sample_target="dbfs:/Volumes/${catalog}/${schema}/${volume}/demo"
runtime_target="dbfs:/Volumes/${catalog}/${schema}/${volume}/runtime"
local_output_dir="${LOCAL_METADATA_OUTPUT_DIR:-local_outputs/legacy_metadata}"

if [ ! -d "$sample_source" ]; then
  echo "Sample metadata folder not found: $sample_source" >&2
  exit 1
fi

databricks_cmd=(databricks)
if [ -n "${DATABRICKS_PROFILE:-}" ]; then
  databricks_cmd+=(--profile "$DATABRICKS_PROFILE")
fi

if ! "${databricks_cmd[@]}" schemas get "${catalog}.${schema}" >/dev/null 2>&1; then
  echo "Creating schema ${catalog}.${schema}"
  "${databricks_cmd[@]}" schemas create "$schema" "$catalog" --comment "Metadata landing schema for Modern Migration Accelerator"
fi

if ! "${databricks_cmd[@]}" volumes read "${catalog}.${schema}.${volume}" >/dev/null 2>&1; then
  echo "Creating managed volume ${catalog}.${schema}.${volume}"
  "${databricks_cmd[@]}" volumes create "$catalog" "$schema" "$volume" MANAGED --comment "Legacy metadata landing volume"
fi

echo "Uploading runtime scripts to /Volumes/${catalog}/${schema}/${volume}/runtime"
"${databricks_cmd[@]}" fs mkdirs "$runtime_target"
"${databricks_cmd[@]}" fs cp --overwrite "src/modern_migration_accelerator/pipelines/run_accelerator.py" "$runtime_target/run_accelerator.py"
"${databricks_cmd[@]}" fs cp --overwrite "src/modern_migration_accelerator/pipelines/run_target_demo.py" "$runtime_target/run_target_demo.py"
"${databricks_cmd[@]}" fs cp --overwrite "src/modern_migration_accelerator/pipelines/run_semantic_index_prep.py" "$runtime_target/run_semantic_index_prep.py"

if [ -n "${LEGACY_METADATA_SOURCE_ROOT:-}" ]; then
  echo "Using customer metadata source: $LEGACY_METADATA_SOURCE_ROOT"
  exit 0
fi

echo "Uploading demo metadata to $sample_source_root"
"${databricks_cmd[@]}" fs rm -r "$sample_target" >/dev/null 2>&1 || true
"${databricks_cmd[@]}" fs cp -r "$sample_source" "$sample_target"

if [ -d "$local_output_dir" ]; then
  echo "Uploading local metadata outputs from $local_output_dir"
  "${databricks_cmd[@]}" fs cp -r "$local_output_dir" "$sample_target/local_outputs"
fi

echo "Demo metadata ready: $sample_source_root"
