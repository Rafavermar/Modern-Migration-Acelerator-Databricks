from __future__ import annotations

import argparse
import sys
from pathlib import Path

SRC_ROOT = Path(__file__).resolve().parents[2]
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from modern_migration_accelerator.pipelines.run_accelerator import quote_identifier, table_name


def get_spark():
    from pyspark.sql import SparkSession

    return SparkSession.builder.appName("modern-migration-target-demo").getOrCreate()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create a small target demo from the generated blueprint.")
    parser.add_argument("--catalog", default="migration_accelerator_dev")
    parser.add_argument("--gold-schema", default="gold")
    parser.add_argument("--demo-schema", default="demo")
    parser.add_argument("--run-id", default=None)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    spark = get_spark()

    spark.sql(f"CREATE SCHEMA IF NOT EXISTS {quote_identifier(args.catalog)}.{quote_identifier(args.demo_schema)}")
    source_table = table_name(args.catalog, args.gold_schema, "target_databricks_blueprint")
    target_table = table_name(args.catalog, args.demo_schema, "target_migration_plan")

    try:
        blueprint = spark.table(source_table)
    except Exception as exc:
        raise ValueError(
            f"Blueprint table {source_table} does not exist. Run the accelerator job first."
        ) from exc
    if args.run_id:
        blueprint = blueprint.where(blueprint.run_id == args.run_id)

    from pyspark.sql import functions as functions

    demo = (
        blueprint.select(
            "run_id",
            "asset_name",
            "legacy_asset_type",
            "target_pattern",
            "target_catalog",
            "target_schema",
            "target_object",
        )
        .withColumn("demo_status", functions.lit("planned"))
        .withColumn("created_at", functions.current_timestamp())
    )

    demo.write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable(
        target_table
    )


if __name__ == "__main__":
    main()
