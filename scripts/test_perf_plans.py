#!/usr/bin/env python3
"""Pins the helpers of perf/plans.py (task #3859, story #3856, AC 3): the query-plan investigation of the four load shapes.

perf/plans.py fetches each shape's compiled query from a running demo API (route /api/<engine>/query), runs EXPLAIN (ANALYZE, BUFFERS)
in PostgreSQL and explain("executionStats") in MongoDB, creates indexes on status and quantity, runs everything again, and writes a
Markdown report. The docker and network parts are not tested here; the parts that turn a query into a statement and a plan into numbers are.
Run: python3 scripts/test_perf_plans.py
"""
import importlib.util
import json
import subprocess
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
PLANS = ROOT / "perf" / "plans.py"


def load_module():
    spec = importlib.util.spec_from_file_location("perf_plans", PLANS)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class LiteralTests(unittest.TestCase):
    def test_literals(self):
        plans = load_module()
        self.assertEqual("NULL", plans.sql_literal(None))
        self.assertEqual("8", plans.sql_literal(8))
        self.assertEqual("1.5", plans.sql_literal(1.5))
        self.assertEqual("true", plans.sql_literal(True))
        self.assertEqual("'acme'", plans.sql_literal("acme"))
        self.assertEqual("'O''Brien'", plans.sql_literal("O'Brien"))

    def test_a_list_is_an_array_literal(self):
        plans = load_module()
        self.assertEqual("ARRAY['shipped', 'delivered']", plans.sql_literal(["shipped", "delivered"]))
        self.assertEqual("ARRAY[1, 2]", plans.sql_literal([1, 2]))

    def test_the_statement_prepares_then_explains_with_the_parameters(self):
        plans = load_module()
        statement = plans.explain_statement('SELECT 1 FROM "orders" WHERE "quantity" > $1 LIMIT $2', [8, 100])
        self.assertEqual('PREPARE q AS SELECT 1 FROM "orders" WHERE "quantity" > $1 LIMIT $2; '
                         "EXPLAIN (ANALYZE, BUFFERS) EXECUTE q(8, 100);", statement)

    def test_a_query_without_parameters_executes_without_a_list(self):
        plans = load_module()
        self.assertTrue(plans.explain_statement("SELECT 1", []).endswith("EXECUTE q;"))


class PlanReadingTests(unittest.TestCase):
    POSTGRES = """Limit  (cost=1.00..2.00 rows=100 width=10) (actual time=0.5..900.2 rows=100 loops=1)
  ->  Gather Merge  (cost=1..2 rows=1 width=1) (actual time=1..2 rows=1 loops=1)
        ->  Parallel Seq Scan on orders  (cost=0.00..1.00 rows=1 width=1) (actual time=0.1..800.0 rows=33333 loops=3)
              Filter: (quantity > 8)
              Rows Removed by Filter: 120000
Planning Time: 0.2 ms
Execution Time: 912.5 ms"""

    def test_postgres_plan_summary(self):
        plans = load_module()
        summary = plans.summarize_postgres(self.POSTGRES)
        self.assertEqual(912.5, summary["execution_ms"])
        self.assertEqual(["Parallel Seq Scan on orders"], summary["scans"])
        self.assertEqual("Limit", summary["top"])

    def test_an_index_scan_is_reported_by_name(self):
        plans = load_module()
        text = "Limit (actual time=0..1 rows=1 loops=1)\n  ->  Index Scan using orders_status_idx on orders (actual time=0..1 rows=1 loops=1)\nExecution Time: 1.5 ms"
        self.assertEqual(["Index Scan using orders_status_idx on orders"], plans.summarize_postgres(text)["scans"])

    def test_a_plan_without_an_execution_time_is_an_error(self):
        plans = load_module()
        with self.assertRaises(ValueError):
            plans.summarize_postgres("nothing useful")

    def test_mongo_explain_summary_from_an_aggregate_cursor_stage(self):
        plans = load_module()
        explain = {"stages": [{"$cursor": {"queryPlanner": {"winningPlan": {"stage": "COLLSCAN"}},
                                           "executionStats": {"nReturned": 10, "executionTimeMillis": 3400, "totalDocsExamined": 1000000, "totalKeysExamined": 0}}},
                              {"$group": {}}]}
        summary = plans.summarize_mongo(explain)
        self.assertEqual("COLLSCAN", summary["stage"])
        self.assertEqual(1000000, summary["docs_examined"])
        self.assertEqual(3400, summary["execution_ms"])

    def test_mongo_explain_summary_with_an_index_below_a_fetch(self):
        plans = load_module()
        explain = {"queryPlanner": {"winningPlan": {"stage": "LIMIT", "inputStage": {"stage": "FETCH", "inputStage": {"stage": "IXSCAN"}}}},
                   "executionStats": {"nReturned": 100, "executionTimeMillis": 12, "totalDocsExamined": 100, "totalKeysExamined": 100}}
        summary = plans.summarize_mongo(explain)
        self.assertEqual("IXSCAN", summary["stage"])
        self.assertEqual(100, summary["keys_examined"])

    def test_mongo_explain_without_statistics_is_an_error(self):
        plans = load_module()
        with self.assertRaises(ValueError):
            plans.summarize_mongo({"ok": 1})


class CountStatementTests(unittest.TestCase):
    """The demo asks for the total row count on every block (includeRowCount: true): SELECT COUNT(*) FROM (<statement without its row window>)."""

    def test_the_row_window_is_removed_and_its_parameters_dropped(self):
        plans = load_module()
        sql, params = plans.count_statement('SELECT "id" FROM "orders" WHERE "quantity" > $1 ORDER BY "id" ASC LIMIT $2 OFFSET $3', [8, 100, 0])
        self.assertEqual('SELECT COUNT(*) FROM (SELECT "id" FROM "orders" WHERE "quantity" > $1 ORDER BY "id" ASC) craticula_count', sql)
        self.assertEqual([8], params)

    def test_a_statement_without_a_row_window_is_wrapped_unchanged(self):
        plans = load_module()
        sql, params = plans.count_statement('SELECT "country" FROM "orders" GROUP BY "country"', [])
        self.assertEqual('SELECT COUNT(*) FROM (SELECT "country" FROM "orders" GROUP BY "country") craticula_count', sql)
        self.assertEqual([], params)


class MongoCommandTests(unittest.TestCase):
    def test_a_plain_pipeline_has_no_options(self):
        plans = load_module()
        pipeline, options = plans.mongo_parts('[{"$match": {"quantity": {"$gt": 8}}}]')
        self.assertEqual([{"$match": {"quantity": {"$gt": 8}}}], pipeline)
        self.assertEqual({}, options)

    def test_a_pipeline_with_a_collation_passes_it_as_an_option(self):
        plans = load_module()
        text = json.dumps({"pipeline": [{"$match": {"status": {"$in": ["shipped"]}}}], "collation": {"locale": "en", "strength": 2}})
        pipeline, options = plans.mongo_parts(text)
        self.assertEqual([{"$match": {"status": {"$in": ["shipped"]}}}], pipeline)
        self.assertEqual({"collation": {"locale": "en", "strength": 2}}, options)


class CliTests(unittest.TestCase):
    def test_missing_containers_are_exit_2(self):
        result = subprocess.run([sys.executable, "-I", str(PLANS)], capture_output=True, text=True, timeout=30)
        self.assertEqual(2, result.returncode)

    def test_an_absolute_report_path_is_refused(self):
        result = subprocess.run([sys.executable, "-I", str(PLANS), "--pg-container", "a", "--mongo-container", "b", "--out", "/an/absolute/report.md"],
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(2, result.returncode)
        self.assertIn("relative", result.stderr)


if __name__ == "__main__":
    unittest.main()
