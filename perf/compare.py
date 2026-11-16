#!/usr/bin/env python3
"""Compares two runs of the same measurements (story #3324, NFR-08, AC 4): is the second within --limit percent (default 10) of the first?

Usage: python3 perf/compare.py <first results dir> <second results dir> [--limit 10]
Each dir is perf/results/<date>/ with compile/results/*-report-full.json and manifest-<engine>-<dataset>.json files. Compared: the mean of
every compile benchmark, and p50, p95, p99 and requests per second of every load run. Exit 0 = all within the limit, 1 = at least one is
not (listed), 2 = a run is missing, unreadable, or the two runs do not hold the same measurements. Tests: scripts/test_perf_page.py.
"""
import argparse
import json
import sys
from pathlib import Path


class RunError(Exception):
    pass


def read_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise RunError(f"{path}: cannot read ({error})") from error


def metrics(results):
    results = Path(results)
    if not results.is_dir():
        raise RunError(f"{results}: not a folder")
    found = {}
    reports = sorted((results / "compile" / "results").glob("*-report-full.json"))
    if len(reports) != 1:
        raise RunError(f"{results}: expected one compile report")
    for benchmark in read_json(reports[0])["Benchmarks"]:
        params = {}
        for pair in benchmark["Parameters"].split("&"):
            key, _, value = pair.partition("=")
            params[key] = value
        found[f"compile {params['Backend']}/{params['Shape']} mean"] = (benchmark["Statistics"]["Mean"], reports[0])
    manifests = sorted(results.glob("manifest-*.json"))
    if not manifests:
        raise RunError(f"{results}: no load manifest")
    for path in manifests:
        manifest = read_json(path)
        for key, label in (("p50_ms", "p50"), ("p95_ms", "p95"), ("p99_ms", "p99"), ("requests_per_second", "requests per second")):
            value = manifest["summary"][key]
            if value is None:
                raise RunError(f"{path}: {label} is missing (did every request fail?)")
            found[f"load {manifest['engine']} {manifest['dataset']} {label}"] = (value, path)
    return found


def compare(first_dir, second_dir, limit=10.0):
    """(number of measurements, the ones more than `limit` percent apart: name, both values, both source files, change in percent)."""
    first, second = metrics(first_dir), metrics(second_dir)
    if set(first) != set(second):
        raise RunError("the two runs do not hold the same measurements")
    outside = []
    for name in sorted(first):
        a, b = first[name][0], second[name][0]
        change = abs(b - a) / a * 100 if a else 0.0
        if change > limit:
            outside.append({"name": name, "first": a, "second": b, "change": change, "first_path": first[name][1], "second_path": second[name][1]})
    return len(first), outside


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("first")
    parser.add_argument("second")
    parser.add_argument("--limit", type=float, default=10.0)
    args = parser.parse_args(argv)
    try:
        total, outside = compare(args.first, args.second, args.limit)
    except (RunError, KeyError, TypeError) as error:
        print(f"compare.py: {error}", file=sys.stderr)
        return 2
    if outside:
        print(f"{len(outside)} of {total} measurements are more than {args.limit:g}% apart:")
        for item in outside:
            print(f"{item['name']}: {item['first']:g} then {item['second']:g}, {item['change']:.1f}% apart")
        return 1
    print(f"all {total} measurements are within {args.limit:g}% of the first run")
    return 0


if __name__ == "__main__":
    sys.exit(main())
