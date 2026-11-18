#!/usr/bin/env python3
"""Compares two runs of the same measurements (story #3324, NFR-08, AC 4) and reports how far apart they are.

Usage: python3 perf/compare.py <first results dir> <second results dir> [--limit 10]
Each dir is perf/results/<date>/ with compile/results/*-report-full.json and manifest-<engine>-<dataset>.json files. Compared: the mean of
every compile benchmark, and p50, p95, p99 and requests per second of every load run. The command lists the measurements that differ by
more than --limit (the listing threshold, a positive number in percent, default 10), largest first, and names the largest difference.
A spread is a result, not a failure. Exit 0 = both runs were read and compared, whatever the spread.
A repeat that is not a separate run is refused with exit 2 and nothing is compared: the same folder, a copy (the same recorded command),
another machine, another commit, a manifest without machine, commit or command, or measurements that are all exactly equal.
Exit 2 also = a run is missing, unreadable or malformed, a figure is not a finite number, the two runs do not hold the same measurements,
or --limit is not a finite number above 0.
Tests: scripts/test_perf_page.py.
"""
import argparse
import json
import math
import sys
from collections import namedtuple
from pathlib import Path


class RunError(Exception):
    pass


def read_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise RunError(f"{path}: cannot read ({error})") from error


SUMMARY = "summary"
LOAD_FIGURES = (("p50_ms", "p50"), ("p95_ms", "p95"), ("p99_ms", "p99"), ("requests_per_second", "requests per second"))
MALFORMED = (KeyError, TypeError, AttributeError, ValueError, IndexError, OverflowError)
COMPILE_MANIFEST_PATH = "compile/manifest-compile.json"
MACHINE_FIELD = "machine"
COMMIT_FIELD = "commit"
COMMAND_FIELD = "command"
REQUIRED_FIELDS = (MACHINE_FIELD, COMMIT_FIELD, COMMAND_FIELD)
UNKNOWN_COMMIT = "unknown"
MIN_COMMIT_LENGTH = 7
SAME_FOLDER = "same folder"
MISSING_FIELD = "missing field"
SAME_COMMANDS = "same commands"
IDENTICAL = "identical measurements"
NOT_THE_SAME_MEASUREMENTS = "the two runs do not hold the same measurements"
FULL_COMPILE = "full-compile"
PREPARED_SCHEMA = "prepared-schema"

Difference = namedtuple("Difference", "name first second change first_path second_path")


def finite_number(value, label, path):
    if value is None:
        raise RunError(f"{path}: {label} is missing (did every request fail?)")
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise RunError(f"{path}: {label} is not a finite number ({value!r})")
    return float(value)


def add_measurement(found, label, value, path):
    if label in found:
        raise RunError(f"{path}: two measurements are named {label!r}")
    found[label] = (value, path)


def parse_parameters(text):
    params = {}
    for pair in text.split("&"):
        key, _, value = pair.partition("=")
        params[key] = value
    return params


def compile_metrics(report_path):
    report = read_json(report_path)
    found = {}
    try:
        benchmarks = report["Benchmarks"]
        if not benchmarks:
            raise RunError(f"{report_path}: holds no benchmark")
        for benchmark in benchmarks:
            params = parse_parameters(benchmark["Parameters"])
            schema_path = params.get("SchemaPath", FULL_COMPILE)
            if schema_path not in (FULL_COMPILE, PREPARED_SCHEMA):
                raise RunError(f"{report_path}: unknown SchemaPath {schema_path!r}")
            suffix = " prepared" if schema_path == PREPARED_SCHEMA else ""
            label = f"compile {params['Backend']}/{params['Shape']}{suffix} mean"
            add_measurement(found, label, finite_number(benchmark["Statistics"]["Mean"], "mean", report_path), report_path)
    except MALFORMED as error:
        raise RunError(f"{report_path}: malformed ({error!r})") from error
    return found


def load_metrics(manifest_path):
    manifest = read_json(manifest_path)
    found = {}
    try:
        for key, label in LOAD_FIGURES:
            value = finite_number(manifest[SUMMARY][key], label, manifest_path)
            found[f"load {manifest['engine']} {manifest['dataset']} {label}"] = (value, manifest_path)
    except MALFORMED as error:
        raise RunError(f"{manifest_path}: malformed ({error!r})") from error
    return found


def metrics(results):
    results = Path(results)
    if not results.is_dir():
        raise RunError(f"{results}: not a folder")
    reports = sorted((results / "compile" / "results").glob("*-report-full.json"))
    if len(reports) != 1:
        raise RunError(f"{results}: expected one compile report")
    manifests = sorted(results.glob("manifest-*.json"))
    if not manifests:
        raise RunError(f"{results}: no load manifest")
    found = compile_metrics(reports[0])
    for path in manifests:
        for label, (value, source) in load_metrics(path).items():
            add_measurement(found, label, value, source)
    return found


def percent_change(a, b):
    if a == 0:
        return 0.0 if b == 0 else math.inf
    return abs(b - a) * 100 / abs(a)


def refuse(check, text):
    raise RunError(f"{check}: {text}")


def check_not_the_same_folder(first_dir, second_dir):
    first, second = Path(first_dir).resolve(), Path(second_dir).resolve()
    if first == second:
        refuse(SAME_FOLDER, f"both runs are {first}")


def run_manifests(results):
    results = Path(results)
    compile_path = results / COMPILE_MANIFEST_PATH
    if not compile_path.is_file():
        refuse(MISSING_FIELD, f"{results}: no compile manifest")
    paths = sorted([compile_path, *results.glob("manifest-*.json")], key=lambda path: path.relative_to(results).as_posix())
    manifests = []
    for path in paths:
        manifest = read_json(path)
        if not isinstance(manifest, dict):
            refuse(MISSING_FIELD, f"{path}: not a JSON object")
        manifests.append((path, manifest))
    return manifests


def check_fields(manifests):
    for path, manifest in manifests:
        for field in REQUIRED_FIELDS:
            value = manifest.get(field)
            if not isinstance(value, str) or not value.strip():
                refuse(MISSING_FIELD, f"{path}: {field}")
        if manifest[COMMIT_FIELD] == UNKNOWN_COMMIT:
            refuse(MISSING_FIELD, f"{path}: {COMMIT_FIELD} is {UNKNOWN_COMMIT}")


def same_commit(first, second):
    if first == second:
        return True
    long_enough = min(len(first), len(second)) >= MIN_COMMIT_LENGTH
    return long_enough and (first.startswith(second) or second.startswith(first))


def single_value(manifests, field, same):
    longest = max((manifest[field] for _, manifest in manifests), key=len)
    for path, manifest in manifests:
        if not same(longest, manifest[field]):
            refuse(field, f"{path} carries {manifest[field]}, another manifest of the run carries {longest}")
    return longest


def check_same_value(field, same, first, second):
    first_value, second_value = single_value(first, field, same), single_value(second, field, same)
    if not same(first_value, second_value):
        refuse(field, f"{first_value} and {second_value}")


def check_machine(first, second):
    check_same_value(MACHINE_FIELD, lambda a, b: a == b, first, second)


def check_commit(first, second):
    check_same_value(COMMIT_FIELD, same_commit, first, second)


def relative_name(path):
    return COMPILE_MANIFEST_PATH if path.parent.name == "compile" else path.name


def check_commands(first, second):
    first_by_name = {relative_name(path): manifest for path, manifest in first}
    second_by_name = {relative_name(path): manifest for path, manifest in second}
    if set(first_by_name) != set(second_by_name):
        raise RunError(NOT_THE_SAME_MEASUREMENTS)
    for name in sorted(first_by_name):
        if first_by_name[name][COMMAND_FIELD] == second_by_name[name][COMMAND_FIELD]:
            refuse(SAME_COMMANDS, f"{name} records the same command in both runs; run the repeat into a fresh folder")


def check_not_all_equal(items):
    if all(item.first == item.second for item in items):
        refuse(IDENTICAL, f"all {len(items)} measurements are exactly equal in both runs")


def compare(first_dir, second_dir, limit=10.0):
    """Reads both runs and returns (the number of measurements, the Difference of each one above `limit` percent (the listing
    threshold, default 10) largest first with ties in name order, the largest Difference overall: the first by name when several tie).
    A zero baseline with a non-zero repeat has change math.inf; two zeros have change 0.0. Raises RunError for any bad input, and for a
    repeat that is not a separate run (same folder, same command, another machine or commit, all figures equal)."""
    check_not_the_same_folder(first_dir, second_dir)
    first, second = metrics(first_dir), metrics(second_dir)
    if set(first) != set(second):
        raise RunError(NOT_THE_SAME_MEASUREMENTS)
    first_manifests, second_manifests = run_manifests(first_dir), run_manifests(second_dir)
    check_fields(first_manifests)
    check_fields(second_manifests)
    check_machine(first_manifests, second_manifests)
    check_commit(first_manifests, second_manifests)
    check_commands(first_manifests, second_manifests)
    items = [Difference(name, first[name][0], second[name][0], percent_change(first[name][0], second[name][0]), first[name][1], second[name][1])
             for name in sorted(first)]
    check_not_all_equal(items)
    outside = sorted((item for item in items if item.change > limit), key=lambda item: item.change, reverse=True)
    return len(items), outside, max(items, key=lambda item: item.change)


def describe(change):
    return "from 0" if math.isinf(change) else f"{change:.1f}% apart"


def difference_line(item):
    return f"{item.name}: {item.first:g} then {item.second:g}, {describe(item.change)}"


def finite_positive(text):
    try:
        value = float(text)
    except ValueError:
        value = math.nan
    if not math.isfinite(value) or value <= 0:
        raise argparse.ArgumentTypeError(f"{text!r} is not a finite number above 0")
    return value


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("first")
    parser.add_argument("second")
    parser.add_argument("--limit", type=finite_positive, default=10.0, help="listing threshold in percent, above 0 (default 10)")
    args = parser.parse_args(argv)
    try:
        total, outside, largest = compare(args.first, args.second, args.limit)
    except RunError as error:
        print(f"compare.py: {error}", file=sys.stderr)
        return 2
    if outside:
        print(f"{len(outside)} of {total} measurements differ by more than {args.limit:g}%:")
        for item in outside:
            print(difference_line(item))
    else:
        print(f"none of the {total} measurements differs by more than {args.limit:g}%")
    print("largest difference: " + difference_line(largest))
    return 0


if __name__ == "__main__":
    sys.exit(main())
