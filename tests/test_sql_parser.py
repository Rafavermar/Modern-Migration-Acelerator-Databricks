from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from modern_migration_accelerator.parsers.sql import extract_sql_references


class SqlParserTests(unittest.TestCase):
    def test_extracts_common_table_references(self) -> None:
        sql = """
        -- ignored comment FROM hidden.table
        SELECT *
        FROM [dbo].[CustomerOrders] o
        JOIN sales.DimCustomer c ON o.customer_id = c.customer_id;

        INSERT INTO mart.FactOrders
        SELECT * FROM staging.orders;
        """

        self.assertEqual(
            extract_sql_references(sql),
            [
                "dbo.customerorders",
                "sales.dimcustomer",
                "mart.factorders",
                "staging.orders",
            ],
        )

    def test_ignores_temp_identifiers(self) -> None:
        sql = "SELECT * FROM #stage JOIN @ids i ON stage.id = i.id"

        self.assertEqual(extract_sql_references(sql), [])


if __name__ == "__main__":
    unittest.main()
