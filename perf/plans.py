#!/usr/bin/env python3
"""Query plans of the four load shapes at 1M rows, before and after two indexes (story #3856, task #3859).

Needs a running demo stack seeded with the rows (see scripts/perf-load.sh: the same compose project and ports) and its API without
public mode. For each shape in examples/demo/smoke it fetches the compiled query from /api/<engine>/query, runs EXPLAIN (ANALYZE, BUFFERS)
in PostgreSQL and explain("executionStats") in MongoDB, creates indexes on status and quantity, runs everything again and writes a
Markdown report. It changes the database it is given (the indexes): use the throwaway stack only.
Usage: python3 perf/plans.py --pg-container <name> --mongo-container <name> [--api-url http://127.0.0.1:5081] [--out docs/feat/3324/query-plans.md]
Exit 0 = report written, 2 = bad arguments or a step failed. Tests: scripts/test_perf_plans.py.
"""
import argparse
import json
import re
import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SMOKE = ROOT / "examples" / "demo" / "smoke"
SHAPES = ("group-by-country", "number-gt", "set-filter-status", "text-contains-sort")
SCAN_NODE = re.compile(r"(?:Parallel )?(?:Seq Scan|Index Scan|Index Only Scan|Bitmap Heap Scan|Bitmap Index Scan)[^(]*?(?=\s+\()")


def sql_literal(value):
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, list):
        return "ARRAY[" + ", ".join(sql_literal(item) for item in value) + "]"
    if isinstance(value, (int, float)):
        return str(value)
    return "'" + str(value).replace("'", "''") + "'"


def explain_statement(text, parameters):
    execute = f"EXECUTE q({', '.join(sql_literal(p) for p in parameters)})" if parameters else "EXECUTE q"
    return f"PREPARE q AS {text}; EXPLAIN (ANALYZE, BUFFERS) {execute};"


def summarize_postgres(plan):
    match = re.search(r"Execution Time:\s*([0-9.]+)\s*ms", plan)
    if not match:
        raise ValueError("the plan has no Execution Time line")
    first = plan.strip().splitlines()[0]
    top = re.split(r"\s{2,}|\s\(", first.strip())[0].strip()
    scans = [m.group(0).strip() for m in SCAN_NODE.finditer(plan)]
    return {"execution_ms": float(match.group(1)), "top": top, "scans": scans}


def find_key(node, key):
    if isinstance(node, dict):
        if key in node:
            return node[key]
        for value in node.values():
            found = find_key(value, key)
            if found is not None:
                return found
    elif isinstance(node, list):
        for value in node:
            found = find_key(value, key)
            if found is not None:
                return found
    return None


def deepest_stage(plan):
    stage = plan.get("stage")
    while isinstance(plan, dict) and "inputStage" in plan:
        plan = plan["inputStage"]
        stage = plan.get("stage", stage)
    return stage


def summarize_mongo(explain):
    stats = find_key(explain, "executionStats")
    winning = find_key(explain, "winningPlan")
    if stats is None or winning is None:
        raise ValueError("the explain output has no executionStats and winningPlan")
    return {
        "stage": deepest_stage(winning),
        "docs_examined": stats.get("totalDocsExamined"),
        "keys_examined": stats.get("totalKeysExamined"),
        "execution_ms": stats.get("executionTimeMillis"),
        "returned": stats.get("nReturned"),
    }


def count_statement(text, parameters):
    """The statement the adapter wraps to count all matching rows: the compiled one without its LIMIT/OFFSET (and their two parameters)."""
    stripped = re.sub(r"\s+LIMIT \$\d+ OFFSET \$\d+\s*$", "", text)
    kept = list(parameters)[:-2] if stripped != text else list(parameters)
    return f"SELECT COUNT(*) FROM ({stripped}) craticula_count", kept


def post_json(url, body):
    request = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.loads(response.read())


def docker_exec(container, *command):
    result = subprocess.run(["docker", "exec", container, *command], capture_output=True, text=True, timeout=900)
    if result.returncode != 0:
        raise RuntimeError(f"docker exec {container} failed: {result.stderr.strip()[:300]}")
    return result.stdout


def postgres_plan(container, compiled):
    out = docker_exec(container, "psql", "-U", "demo", "-d", "demo", "-At", "-c", explain_statement(compiled["text"], compiled["parameters"]))
    return out


def mongo_parts(text):
    """The compiled Mongo query is a pipeline, or an object with the pipeline and a collation to pass as an option."""
    parsed = json.loads(text)
    if isinstance(parsed, dict):
        return parsed["pipeline"], {key: value for key, value in parsed.items() if key != "pipeline"}
    return parsed, {}


def mongo_explain(container, query_text):
    pipeline, options = mongo_parts(query_text)
    script = f'JSON.stringify(db.getSiblingDB("demo").orders.explain("executionStats").aggregate({json.dumps(pipeline)}, {json.dumps(options)}))'
    out = docker_exec(container, "mongosh", "--quiet", "--eval", script)
    return json.loads(out.strip().splitlines()[-1])


def collect(api_url, pg, mongo):
    results = {}
    for shape in SHAPES:
        body = (SMOKE / f"{shape}.json").read_bytes()
        row = {}
        pg_compiled = post_json(f"{api_url}/api/postgres/query", body)
        row["postgres"] = summarize_postgres(postgres_plan(pg, pg_compiled))
        count_sql, count_params = count_statement(pg_compiled["text"], pg_compiled["parameters"])
        row["postgres"]["count_ms"] = summarize_postgres(postgres_plan(pg, {"text": count_sql, "parameters": count_params}))["execution_ms"]
        mongo_compiled = post_json(f"{api_url}/api/mongo/query", body)
        row["mongo"] = summarize_mongo(mongo_explain(mongo, mongo_compiled["text"]))
        results[shape] = row
    return results


def create_indexes(pg, mongo):
    docker_exec(pg, "psql", "-U", "demo", "-d", "demo", "-c",
                "CREATE INDEX IF NOT EXISTS orders_status_idx ON orders (status); CREATE INDEX IF NOT EXISTS orders_quantity_idx ON orders (quantity); ANALYZE orders;")
    docker_exec(mongo, "mongosh", "--quiet", "--eval",
                'db.getSiblingDB("demo").orders.createIndex({status: 1}); db.getSiblingDB("demo").orders.createIndex({quantity: 1})')


def report(before, after):
    lines = ["# Query plans of the four load shapes at 1M rows", "", "Classification: Restricted", "",
             "Generated by `perf/plans.py` (story #3856, task #3859) on one local stack with 1,000,000 rows. The numbers are one run each, on a "
             "development machine with other things running; read the plans, not the milliseconds. \"After\" = indexes on `status` and `quantity` "
             "added (the seed already has indexes on `country`, `category` and `ordered_at`).", "",
             "## PostgreSQL", "",
             "`Page ms` is the query that returns the 100 rows; `Count ms` is the `SELECT COUNT(*) FROM (...)` the demo also runs on every block "
             "(`includeRowCount: true`).", "",
             "| Shape | Before: scan nodes | Page ms | Count ms | After: scan nodes | Page ms | Count ms |", "|---|---|---|---|---|---|---|"]
    for shape in SHAPES:
        b, a = before[shape]["postgres"], after[shape]["postgres"]
        lines.append(f"| {shape} | {'; '.join(b['scans']) or b['top']} | {b['execution_ms']:.0f} | {b['count_ms']:.0f} | "
                     f"{'; '.join(a['scans']) or a['top']} | {a['execution_ms']:.0f} | {a['count_ms']:.0f} |")
    lines += ["", "## MongoDB", "", "| Shape | Before: stage | Docs examined | Before ms | After: stage | Docs examined | After ms |", "|---|---|---|---|---|---|---|"]
    for shape in SHAPES:
        b, a = before[shape]["mongo"], after[shape]["mongo"]
        lines.append(f"| {shape} | {b['stage']} | {b['docs_examined']} | {b['execution_ms']} | {a['stage']} | {a['docs_examined']} | {a['execution_ms']} |")
    return "\n".join(lines) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--pg-container", required=True)
    parser.add_argument("--mongo-container", required=True)
    parser.add_argument("--api-url", default="http://127.0.0.1:5081")
    parser.add_argument("--out", default="docs/feat/3324/query-plans.md")
    args = parser.parse_args(argv)
    if args.out.startswith("/"):
        print("plans.py: --out must be a path relative to the repository (an absolute one would publish a home directory)", file=sys.stderr)
        return 2
    try:
        before = collect(args.api_url, args.pg_container, args.mongo_container)
        create_indexes(args.pg_container, args.mongo_container)
        after = collect(args.api_url, args.pg_container, args.mongo_container)
    except (RuntimeError, ValueError, OSError, json.JSONDecodeError) as error:
        print(f"plans.py: {error}", file=sys.stderr)
        return 2
    out = ROOT / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(report(before, after), encoding="utf-8")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
