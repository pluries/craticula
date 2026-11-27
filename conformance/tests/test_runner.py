"""Tests of conformance/run.py. Every AC-2 / AC-3 rule and every protocol failure of spec/conformance-runner.md has a
case here; trees are built in a temp dir and a Python fake driver stands in for an implementation (AC-4)."""
import contextlib
import io
import json
import os
import shlex
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(HERE.parent))

import run  # noqa: E402

FAKE = HERE / "fake_driver.py"
REAL_FIXTURES = ROOT / "spec" / "fixtures"


class RunnerCase(unittest.TestCase):
    timeout = "5"

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self.tree = self.tmp / "fixtures"
        self.tree.mkdir()

    def fixture(self, category, slug, expected=None, extra=None):
        """expected: {backend: raw JSON text}; extra: {relative file: text} (e.g. expected/rejection.json)."""
        d = self.tree / category / slug
        (d / "expected").mkdir(parents=True)
        (d / "schema.json").write_text('{"table":"t"}')
        (d / "agGridRequest.json").write_text('{"startRow":0}')
        for backend, raw in (expected or {}).items():
            (d / "expected" / f"{backend}.artifact.json").write_text(raw)
        for rel, text in (extra or {}).items():
            (d / rel).write_text(text)
        return f"{category}/{slug}"

    def answers(self, table):
        p = self.tmp / "answers.json"
        p.write_text(json.dumps(table))
        return str(p)

    def go(self, *driver_args, runner_args=(), fixtures=None):
        """Run the runner in-process; returns (exit code, stdout)."""
        driver = shlex.join([sys.executable, str(FAKE), "--fixtures", str(fixtures or self.tree), *driver_args])
        argv = ["--driver", driver, "--fixtures", str(fixtures or self.tree), "--timeout", self.timeout, *runner_args]
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = run.main(argv)
        return code, out.getvalue() + err.getvalue()


SQL = '{"dialect":"postgres","sql":"SELECT 1","params":["19.99",1]}'


class EqualityRules(RunnerCase):  # AC-1, AC-2
    def one(self, backend, expected, actual, mode_args=()):
        self.n = getattr(self, "n", 0) + 1
        fid = self.fixture("c", f"{self.n:03d}-x", {backend: expected})
        table = self.answers({f"{fid}#{backend}": {"artifact": actual}})
        return self.go("--answers", table, "--backends", backend, *mode_args)

    def test_identical_artifact_passes(self):
        code, out = self.one("postgres", SQL, SQL)
        self.assertEqual(code, 0, out)
        self.assertIn("RESULT: PASS", out)

    def test_ac1_mismatch_names_fixture_backend_path_and_values(self):
        code, out = self.one("postgres", SQL, SQL.replace("SELECT 1", "SELECT 2"))
        self.assertEqual(code, 1)
        for needle in ("FAIL c/001-x#postgres", "$.sql", '"SELECT 1"', '"SELECT 2"'):
            self.assertIn(needle, out)

    def test_sql_param_string_is_not_a_number(self):
        code, out = self.one("postgres", SQL, SQL.replace('"19.99"', "19.99"))
        self.assertEqual(code, 1)
        self.assertIn("$.params[0]", out)

    def test_sql_param_order_counts(self):
        code, _ = self.one("postgres", SQL, SQL.replace('["19.99",1]', '[1,"19.99"]'))
        self.assertEqual(code, 1)

    def test_sql_wrapper_member_order_is_not_significant(self):
        code, out = self.one("postgres", SQL, '{"params":["19.99",1],"sql":"SELECT 1","dialect":"postgres"}')
        self.assertEqual(code, 0, out)

    def test_sql_missing_member_fails(self):
        code, out = self.one("postgres", SQL, '{"dialect":"postgres","sql":"SELECT 1"}')
        self.assertEqual(code, 1)
        self.assertIn("$.params", out)

    def test_number_one_and_one_point_zero_differ(self):
        code, _ = self.one("postgres", SQL, SQL.replace(",1]", ",1.0]"))
        self.assertEqual(code, 1)

    def test_number_exponent_form_differs(self):
        code, _ = self.one("sqlite", SQL.replace("1]", "100]"), SQL.replace("1]", "1E2]"))
        self.assertEqual(code, 1)

    def test_mongo_key_order_counts(self):
        exp = '[{"$match":{"a":1,"b":2}}]'
        code, out = self.one("mongo", exp, '[{"$match":{"b":2,"a":1}}]')
        self.assertEqual(code, 1)
        self.assertIn("$[0].$match", out)
        code, out = self.one("mongo", exp, exp)
        self.assertEqual(code, 0, out)

    def test_mongo_sort_document_key_order_is_the_tiebreak(self):
        code, _ = self.one("mongo", '[{"$sort":{"a":1,"b":-1}}]', '[{"$sort":{"b":-1,"a":1}}]')
        self.assertEqual(code, 1)

    def test_search_object_key_order_is_ignored_at_every_depth(self):
        exp = '{"query":{"bool":{"must":[{"term":{"a":1,"b":2}}],"filter":[]}},"size":10}'
        act = '{"size":10,"query":{"bool":{"filter":[],"must":[{"term":{"b":2,"a":1}}]}}}'
        code, out = self.one("search", exp, act)
        self.assertEqual(code, 0, out)

    def test_search_array_order_counts(self):
        code, out = self.one("search", '{"must":[{"a":1},{"b":2}]}', '{"must":[{"b":2},{"a":1}]}')
        self.assertEqual(code, 1)
        self.assertIn("$.must[0]", out)

    def test_search_extra_and_missing_keys_fail(self):
        self.assertEqual(self.one("search", '{"a":1}', '{"a":1,"b":2}')[0], 1)
        self.assertEqual(self.one("search", '{"a":1,"b":2}', '{"a":1}')[0], 1)

    def test_array_length_difference_fails(self):
        code, out = self.one("search", "[1,2,3]", "[1,2]")
        self.assertEqual(code, 1)
        self.assertIn("<missing>", out)

    def test_type_difference_fails(self):
        self.assertEqual(self.one("search", '{"a":true}', '{"a":1}')[0], 1)
        self.assertEqual(self.one("search", '{"a":null}', '{"a":"null"}')[0], 1)
        self.assertEqual(self.one("search", '{"a":"1"}', '{"a":1}')[0], 1)


class Coverage(RunnerCase):  # AC-3
    def setUp(self):
        super().setUp()
        self.fid = self.fixture("c", "001-x", {"postgres": SQL, "mongo": "[]", "search": "{}"})

    def test_undeclared_backends_are_not_graded_and_never_pass(self):
        code, out = self.go("--backends", "postgres")
        self.assertEqual(code, 0, out)
        row = {line.split()[0]: line.split()[1:] for line in out.splitlines() if line[:5] in ("postg", "mongo", "searc")}
        self.assertEqual(row["postgres"], ["1", "0", "0"])
        self.assertEqual(row["mongo"], ["0", "0", "1"])
        self.assertEqual(row["search"], ["0", "0", "1"])

    def test_declared_backend_answered_with_error_fails(self):
        table = self.answers({f"{self.fid}#mongo": {"error": {"kind": "Unsupported", "message": "no $facet"}}})
        code, out = self.go("--answers", table)
        self.assertEqual(code, 1)
        self.assertIn("FAIL c/001-x#mongo", out)
        self.assertIn("Unsupported: no $facet", out)

    def test_runner_never_sends_a_case_without_an_expected_artifact(self):
        self.fixture("c", "002-only-mongo", {"mongo": "[]"})
        code, out = self.go("--backends", "postgres")
        self.assertEqual(code, 0, out)  # 002 has nothing for postgres: nothing sent, nothing failed

    def test_unreadable_expected_file_is_a_usage_error(self):
        (self.tree / "c" / "001-x" / "expected" / "mongo.artifact.json").write_text("{not json")
        code, out = self.go()
        self.assertEqual(code, 2)
        self.assertIn("cannot read", out)
        self.assertNotIn("RESULT", out)  # nothing was sent: the driver was never started

    def test_only_filters_by_fixture_and_by_case(self):
        self.fixture("c", "002-y", {"postgres": SQL})
        code, out = self.go(runner_args=("--only", "c/002-*"))
        self.assertEqual(code, 0, out)
        self.assertRegex(out, r"(?m)^postgres\s+1\s+0\s+0$")
        self.assertNotRegex(out, r"(?m)^(mongo|search) ")
        code, out = self.go(runner_args=("--only", "c/001-x#mongo", "--only", "c/002-y#postgres"))
        self.assertEqual(code, 0, out)
        self.assertRegex(out, r"(?m)^mongo\s+1\s+0\s+0$")
        self.assertRegex(out, r"(?m)^postgres\s+1\s+0\s+0$")  # 001-x#postgres left out
        self.assertNotRegex(out, r"(?m)^search ")

    def test_only_that_selects_no_artifact_is_a_usage_error(self):  # spec §6: an empty graded set never passes
        self.fixture("c", "002-rej", extra={"expected/rejection.json": "{}"})
        for glob in ("nothing/*", "c/001-x#oracle"):
            code, out = self.go(runner_args=("--only", glob))
            self.assertEqual(code, 2, (glob, out))
            self.assertIn("no expected artifact matches --only", out)

    def test_no_selected_case_in_a_declared_backend_exits_2(self):
        report = self.tmp / "report.json"
        code, out = self.go("--backends", "oracle", runner_args=("--json", str(report)))
        self.assertEqual(code, 2, out)
        self.assertIn("RESULT: NOTHING GRADED", out)
        self.assertRegex(out, r"(?m)^postgres\s+0\s+0\s+1$")
        self.assertEqual(json.loads(report.read_text())["status"], "nothing-graded")


class Enumeration(RunnerCase):
    def test_out_of_tier_fixtures_are_listed_not_counted(self):
        self.fixture("c", "001-x", {"postgres": SQL})
        self.fixture("c", "002-rej", extra={"expected/rejection.json": "{}"})
        self.fixture("c", "003-csv", extra={"expected/export.csv": "a\n", "rowStream.json": "[]"})
        self.fixture("c", "004-rows", extra={"dataset.json": "[]"})
        self.fixture("c", "005-empty")
        (self.tree / "schemas").mkdir()
        (self.tree / "schemas" / "x.schema.json").write_text("{}")
        code, out = self.go("--backends", "postgres")
        self.assertEqual(code, 0, out)
        self.assertIn("out of tier (2)", out)
        for needle in ("c/004-rows  execution equality (T-1b)", "c/005-empty  no graded file"):
            self.assertIn(needle, out)
        self.assertNotIn("c/002-rej", out.split("out of tier")[1])  # graded kinds now, not out of tier (spec §1)
        self.assertNotIn("c/003-csv", out.split("out of tier")[1])
        self.assertNotIn("schemas", out)

    def test_writer_output_beside_a_graded_artifact_is_graded_too(self):  # spec §1: by content, not by directory
        self.fixture("c", "001-csv", {"postgres": SQL}, extra={"expected/export.csv": "a\n", "rowStream.json": "[]"})
        code, out = self.go("--backends", "postgres")
        self.assertEqual(code, 0, out)
        self.assertRegex(out, r"(?m)^postgres\s+1\s+0\s+0$")
        self.assertRegex(out, r"(?m)^writer\s+0\s+0\s+1$")  # no capability declared: not graded, never passed
        self.assertNotIn("out of tier", out)

    def test_unknown_backend_stem_is_a_usage_error(self):
        self.fixture("c", "001-x", {"postgres": SQL, "db2": "{}"})
        code, out = self.go()
        self.assertEqual(code, 2)
        self.assertIn("db2", out)

    def test_missing_or_empty_fixture_tree_is_a_usage_error(self):
        self.assertEqual(self.go(fixtures=self.tmp / "nope")[0], 2)
        self.assertEqual(self.go()[0], 2)  # the tree exists and is empty

    def test_json_report(self):
        self.fixture("c", "001-x", {"postgres": SQL, "mongo": "[]"})
        self.fixture("c", "002-rej", extra={"expected/rejection.json": "{}"})
        report = self.tmp / "report.json"
        code, out = self.go("--backends", "postgres", runner_args=("--json", str(report)))
        self.assertEqual(code, 0, out)
        data = json.loads(report.read_text())
        self.assertEqual(data["status"], "pass")
        self.assertEqual(data["totals"]["postgres"], {"passed": 1, "failed": 0, "notGraded": 0})
        self.assertEqual(data["totals"]["mongo"]["notGraded"], 1)
        self.assertEqual(data["hello"]["impl"], "fake")
        self.assertEqual(data["outOfTier"], [])
        self.assertEqual(data["totals"]["rejection"], {"passed": 0, "failed": 0, "notGraded": 1})

    def test_json_report_carries_failures(self):
        fid = self.fixture("c", "001-x", {"postgres": SQL})
        table = self.answers({f"{fid}#postgres": {"artifact": SQL.replace("SELECT 1", "SELECT 2")}})
        report = self.tmp / "report.json"
        code, _ = self.go("--answers", table, runner_args=("--json", str(report)))
        self.assertEqual(code, 1)
        failure = json.loads(report.read_text())["failures"][0]
        self.assertEqual((failure["id"], failure["path"]), (f"{fid}#postgres", "$.sql"))


class ProtocolFailures(RunnerCase):  # spec §2.4 — each exits 2 and names what is left unanswered
    def setUp(self):
        super().setUp()
        for i in range(1, 5):
            self.fixture("c", f"00{i}-x", {"postgres": SQL})

    def expect_failure(self, *driver_args, needle, unanswered=None, timeout=None):
        if timeout:
            self.timeout = timeout
        code, out = self.go(*driver_args)
        self.assertEqual(code, 2, out)
        self.assertIn("RESULT: PROTOCOL FAILURE", out)
        self.assertIn(needle, out)
        if unanswered == 0:
            self.assertNotIn("unanswered requests", out)
        elif unanswered is not None:
            self.assertIn(f"unanswered requests ({unanswered})", out)
        return out

    def test_item1_invalid_hello(self):
        self.expect_failure("--mode", "bad-hello", needle="not a hello")

    def test_item1_hello_with_unknown_backend(self):
        self.expect_failure("--backends", "postgres,db2", needle="non-empty backends list")

    def test_item1_hello_with_no_backends_declared(self):
        self.expect_failure("--backends", "", needle="non-empty backends list")

    def test_item1_no_hello_before_the_deadline(self):
        self.expect_failure("--mode", "hang-hello", needle="no hello within 0.5 s", timeout="0.5")

    def test_item1_driver_that_never_says_hello_and_exits(self):
        self.expect_failure("--mode", "exit-silently", needle="stopped before the hello")

    def test_item1_driver_that_stays_silent_gets_the_hello_deadline(self):
        self.expect_failure("--mode", "no-hello", needle="no hello within 0.5 s", timeout="0.5")

    def test_item2_non_json_first_line(self):
        self.expect_failure("--mode", "hello-garbage", needle="not JSON")

    def test_item2_non_json_response_line(self):
        self.expect_failure("--mode", "non-json", needle="not JSON", unanswered=3)

    def test_item2_json_that_is_not_an_object(self):
        self.expect_failure("--mode", "not-object", needle="not a JSON object", unanswered=3)

    def test_item3_unsolicited_line_before_the_awaited_response(self):
        self.expect_failure("--mode", "unsolicited", needle='"nobody#postgres"', unanswered=3)

    def test_item3_repeated_out_of_order_id(self):
        out = self.expect_failure("--mode", "repeat-id", needle="'c/002-x#postgres' was awaited", unanswered=3)
        self.assertIn('response id "c/001-x#postgres"', out)  # the id of the request already answered

    def test_item3_unknown_id(self):
        self.expect_failure("--mode", "unknown-id", needle='"nope"', unanswered=3)

    def test_item3_response_with_neither_artifact_nor_error(self):
        self.expect_failure("--mode", "neither", needle="neither a lone artifact", unanswered=3)

    def test_item3_response_with_both_artifact_and_error(self):
        self.expect_failure("--mode", "both", needle="neither a lone artifact", unanswered=3)

    def test_item3_line_after_the_last_response(self):
        self.expect_failure("--mode", "trailing", needle="unexpected line after the last response", unanswered=0)

    def test_item4_response_timeout(self):
        out = self.expect_failure("--mode", "hang", needle="no response within 0.5 s", unanswered=2, timeout="0.5")
        self.assertIn("c/003-x#postgres", out)

    def test_item5_crash_mid_session(self):
        out = self.expect_failure("--mode", "crash", needle="exit status 1", unanswered=2)
        self.assertIn("c/003-x#postgres", out)
        self.assertIn("c/004-x#postgres", out)

    def test_item5_clean_exit_before_the_session_ends(self):
        self.expect_failure("--mode", "early-exit", needle="exit status 0", unanswered=2)

    def test_item5_non_zero_exit_at_the_end(self):
        self.expect_failure("--mode", "exit-nonzero", needle="exited with status 3", unanswered=0)

    def test_item5_driver_that_does_not_exit_after_stdin_closes(self):
        self.expect_failure("--mode", "no-exit", needle="did not exit", unanswered=0, timeout="0.5")

    @unittest.skipUnless(os.name == "posix", "the launcher here is sh; Windows ends the tree with taskkill /T")
    def test_timeout_ends_a_launcher_driver_and_the_child_it_started(self):
        # `sh -c '<driver>; true'` forks the driver like dotnet run / npx / go run do; the run must still end, and the
        # hung child must not outlive it (spec §2.4)
        pid_file = self.tmp / "driver.pid"
        inner = shlex.join([sys.executable, str(FAKE), "--fixtures", str(self.tree), "--mode", "hang",
                            "--pid-file", str(pid_file)])
        argv = [sys.executable, str(HERE.parent / "run.py"), "--driver", shlex.join(["sh", "-c", inner + "; true"]),
                "--fixtures", str(self.tree), "--timeout", "0.5"]
        try:
            p = subprocess.run(argv, capture_output=True, text=True, timeout=30)
            self.assertEqual(p.returncode, 2, p.stdout + p.stderr)
            self.assertIn("no response within 0.5 s", p.stdout)
            pid = int(pid_file.read_text())
            deadline = time.monotonic() + 5
            while self._alive(pid) and time.monotonic() < deadline:
                time.sleep(0.05)
            self.assertFalse(self._alive(pid), "the driver's child outlived the run")
        finally:
            if pid_file.exists() and self._alive(int(pid_file.read_text())):
                os.kill(int(pid_file.read_text()), 9)

    @staticmethod
    def _alive(pid):
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        return True

    def test_long_unanswered_list_is_truncated_in_text_and_complete_in_json(self):
        for i in range(5, 40):
            self.fixture("c", f"0{i}-x", {"postgres": SQL})
        report = self.tmp / "report.json"
        code, out = self.go("--mode", "crash", runner_args=("--json", str(report)))
        self.assertEqual(code, 2)
        self.assertIn("... and 17 more", out)
        data = json.loads(report.read_text())
        self.assertEqual(len(data["unanswered"]), 37)
        self.assertEqual(data["status"], "protocol-failure")


class Usage(unittest.TestCase):
    def test_driver_that_cannot_start_is_a_usage_error(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "c" / "001-x" / "expected").mkdir(parents=True)
            (Path(d) / "c" / "001-x" / "expected" / "postgres.artifact.json").write_text(SQL)
            (Path(d) / "c" / "001-x" / "schema.json").write_text("{}")
            (Path(d) / "c" / "001-x" / "agGridRequest.json").write_text("{}")
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                code = run.main(["--driver", "/nonexistent/driver", "--fixtures", d])
            self.assertEqual(code, 2)
            self.assertIn("cannot start driver", err.getvalue())

    def test_empty_driver_command_is_a_usage_error(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            code = run.main(["--driver", " ", "--fixtures", str(REAL_FIXTURES), "--only", "operators/*"])
        self.assertEqual(code, 2)
        self.assertIn("empty command", err.getvalue())

    def test_driver_command_keeps_windows_backslashes(self):  # spec §9: the OS parses it, shlex would eat them
        cmd = r"dotnet C:\work\Driver.dll --flag"
        self.assertEqual(run.driver_argv(cmd, posix=False), cmd)
        self.assertEqual(run.driver_argv("dotnet 'a b/D.dll'", posix=True), ["dotnet", "a b/D.dll"])

    def test_missing_driver_argument_exits_2_from_the_command_line(self):
        p = subprocess.run([sys.executable, str(HERE.parent / "run.py")], capture_output=True, text=True)
        self.assertEqual(p.returncode, 2)
        self.assertIn("--driver", p.stderr)


class LiteralJson(unittest.TestCase):
    def test_round_trip_keeps_number_text_and_key_order(self):
        text = '{"b":1.0,"a":[1,1E2,-0,"1",true,null,{"z":0.10,"y":2}],"c":"\\u00e9\\n"}'
        self.assertEqual(run.dumps(run.parse_json(text)), '{"b":1.0,"a":[1,1E2,-0,"1",true,null,{"z":0.10,"y":2}],'
                                                         '"c":"\\u00e9\\n"}')

    def test_nan_and_infinity_are_rejected(self):
        for bad in ("NaN", "Infinity", "[-Infinity]"):
            with self.assertRaises(ValueError):
                run.parse_json(bad)

    def test_requests_are_single_line_ascii(self):
        line = run.dumps(run.parse_json('{"s":"é\\n\\ud83d\\ude00"}'))
        self.assertTrue(line.isascii() and "\n" not in line)
        self.assertEqual(json.loads(line)["s"], "é\n😀")


@unittest.skipUnless(REAL_FIXTURES.is_dir(), "spec/fixtures not present")
class RealFixtureSuite(RunnerCase):
    def test_fake_driver_answering_from_the_expected_files_passes_every_graded_case(self):
        total = len(list(REAL_FIXTURES.glob("*/*/expected/*.artifact.json")))
        self.assertGreater(total, 600)
        self.timeout = "30"
        code, out = self.go(fixtures=REAL_FIXTURES)
        self.assertEqual(code, 0, out[-2000:])
        passed = sum(int(line.split()[1]) for line in out.splitlines() if line.split()[:1] and line.split()[0] in run.BACKENDS)
        self.assertEqual(passed, total)
        self.assertIn("RESULT: PASS", out)

    def test_a_driver_declaring_one_backend_leaves_the_rest_not_graded(self):
        self.timeout = "30"
        code, out = self.go("--backends", "search", fixtures=REAL_FIXTURES)
        self.assertEqual(code, 0, out[-2000:])
        self.assertIn("postgres", out)
        self.assertNotIn("RESULT: FAIL", out)


REJECTION = '{"rejectedAt":"allowlist","reason":"unknown-field","note":"n"}'
ROWS = '{"columns":["a"],"rows":[{"a":"x"}]}'


class RejectionGrading(RunnerCase):
    """spec/conformance-runner.md §2.2, §4.1: rejection cases (feature 009, US1)."""

    def tree_with_rejection(self):
        return self.fixture("adv", "001-x", extra={"expected/rejection.json": REJECTION})

    def test_US1_AS1_the_same_stage_and_reason_passes(self):
        self.tree_with_rejection()
        code, out = self.go("--caps", "rejection")
        self.assertEqual(code, 0, out)
        self.assertRegex(out, r"(?m)^rejection\s+1\s+0\s+0$")

    def test_US1_AS2_a_different_reason_fails_and_names_both_pairs(self):
        self.tree_with_rejection()
        code, out = self.go("--caps", "rejection", "--mode", "wrong-reason")
        self.assertEqual(code, 1, out)
        self.assertIn("FAIL adv/001-x#rejection", out)
        self.assertIn("unknown-field", out)
        self.assertIn("malformed-request", out)

    def test_US1_AS2_a_different_stage_fails(self):
        self.tree_with_rejection()
        code, out = self.go("--caps", "rejection", "--mode", "wrong-stage")
        self.assertEqual(code, 1, out)
        self.assertIn("allowlist", out)
        self.assertIn("resourceLimits", out)

    def test_US1_AS2_an_error_without_the_pair_fails(self):
        self.tree_with_rejection()
        code, out = self.go("--caps", "rejection", "--mode", "no-pair")
        self.assertEqual(code, 1, out)
        self.assertIn("rejectedAt", out)

    def test_US1_AS3_an_artifact_for_a_rejection_case_fails_as_accepted(self):
        self.tree_with_rejection()
        code, out = self.go("--caps", "rejection", "--mode", "accepts")
        self.assertEqual(code, 1, out)
        self.assertIn("accepted a request that must be rejected", out)

    def test_US1_AS4_rejections_are_graded_and_no_longer_out_of_tier(self):
        self.fixture("adv", "001-x", extra={"expected/rejection.json": REJECTION})
        self.fixture("adv", "002-y", {"postgres": SQL}, extra={"expected/rejection.json": REJECTION})
        report = self.tmp / "report.json"
        code, out = self.go("--caps", "rejection", runner_args=("--json", str(report)))
        self.assertEqual(code, 0, out)
        self.assertRegex(out, r"(?m)^rejection\s+2\s+0\s+0$")
        self.assertNotIn("rejection (SEC-6)", out)
        self.assertEqual(json.loads(report.read_text())["totals"]["rejection"]["passed"], 2)

    def test_US1_AS6_a_driver_without_the_capability_leaves_rejections_not_graded(self):
        self.tree_with_rejection()
        self.fixture("c", "001-x", {"postgres": SQL})
        code, out = self.go()
        self.assertEqual(code, 0, out)
        self.assertRegex(out, r"(?m)^rejection\s+0\s+0\s+1$")
        self.assertRegex(out, r"(?m)^postgres\s+1\s+0\s+0$")

    def test_a_capability_outside_the_closed_set_is_a_protocol_failure(self):
        self.tree_with_rejection()
        code, out = self.go("--caps", "magic")
        self.assertEqual(code, 2, out)
        self.assertIn("capabilit", out)

    def test_a_rejection_run_with_nothing_else_still_grades(self):
        self.tree_with_rejection()
        code, out = self.go("--caps", "rejection", "--backends", "oracle")
        self.assertEqual(code, 0, out)

    @unittest.skipUnless(REAL_FIXTURES.is_dir(), "spec/fixtures not present")
    def test_US1_AS5_every_real_rejection_fixture_is_sent_and_graded(self):
        expected = len(list(REAL_FIXTURES.glob("*/*/expected/rejection.json")))
        self.assertGreater(expected, 20)
        self.timeout = "30"
        code, out = self.go("--caps", "rejection", fixtures=REAL_FIXTURES)
        self.assertEqual(code, 0, out[-1500:])
        self.assertRegex(out, rf"(?m)^rejection\s+{expected}\s+0\s+0$")


class WriterGrading(RunnerCase):
    """spec/conformance-runner.md §2.2, §4.2: CSV and TSV bytes (feature 009, US2)."""

    BOM_CSV = b"\xef\xbb\xbfa\r\nx\r\n"

    def tree_with_writer(self, name="001-x", expected=None, extra=None):
        fid = self.fixture("pe", name, extra={"rowStream.json": ROWS, **(extra or {})})
        (self.tree / "pe" / name / "expected" / "export.csv").write_bytes(expected if expected is not None else self.BOM_CSV)
        return fid

    def test_US2_AS1_identical_bytes_pass(self):
        self.tree_with_writer()
        code, out = self.go("--caps", "writer")
        self.assertEqual(code, 0, out)
        self.assertRegex(out, r"(?m)^writer\s+1\s+0\s+0$")

    def test_US2_AS1_a_tsv_expected_file_is_graded_like_a_csv_one(self):
        self.fixture("pe", "002-tab", extra={"rowStream.json": ROWS})
        (self.tree / "pe" / "002-tab" / "expected" / "export.tsv").write_bytes(b"a\r\nx\r\n")
        code, out = self.go("--caps", "writer")
        self.assertEqual(code, 0, out)

    def test_US2_AS2_a_differing_byte_fails_with_its_offset(self):
        self.tree_with_writer()
        code, out = self.go("--caps", "writer", "--mode", "flip-byte")
        self.assertEqual(code, 1, out)
        self.assertIn("FAIL pe/001-x#writer", out)
        self.assertRegex(out, r"first differing byte at offset \d+")

    def test_US2_AS3_a_missing_bom_fails(self):
        self.tree_with_writer()
        code, out = self.go("--caps", "writer", "--mode", "drop-bom")
        self.assertEqual(code, 1, out)
        self.assertIn("offset 0", out)

    def test_US2_AS3_lf_where_crlf_is_expected_fails(self):
        self.tree_with_writer()
        code, out = self.go("--caps", "writer", "--mode", "lf-endings")
        self.assertEqual(code, 1, out)

    def test_US2_AS3_a_shorter_answer_fails_at_the_end_of_the_shorter_side(self):
        self.tree_with_writer()
        table = self.answers({"pe/001-x#writer": {"bytes": "77u/YQ0K"}})  # the BOM, "a", CRLF: the row is missing
        code, out = self.go("--caps", "writer", "--answers", table)
        self.assertEqual(code, 1, out)
        self.assertIn("end of the actual bytes", out)

    def test_US2_AS4_writer_config_reaches_the_driver_unchanged(self):
        config = '{"delimiter":";","bom":false}'
        self.tree_with_writer(expected=config.encode(), extra={"writerConfig.json": config})
        code, out = self.go("--caps", "writer", "--mode", "echo-config")
        self.assertEqual(code, 0, out)

    def test_US2_AS4_without_a_config_file_none_is_sent(self):
        self.tree_with_writer(expected=b"null")
        code, out = self.go("--caps", "writer", "--mode", "echo-config")
        self.assertEqual(code, 0, out)

    def test_a_writer_error_answer_fails_the_case(self):
        self.tree_with_writer()
        code, out = self.go("--caps", "writer", "--mode", "writer-error")
        self.assertEqual(code, 1, out)
        self.assertIn("CsvWriterException", out)

    def test_US2_AS6_a_driver_without_the_capability_leaves_writer_cases_not_graded(self):
        self.tree_with_writer()
        self.fixture("c", "001-x", {"postgres": SQL})
        code, out = self.go()
        self.assertEqual(code, 0, out)
        self.assertRegex(out, r"(?m)^writer\s+0\s+0\s+1$")

    @unittest.skipUnless(REAL_FIXTURES.is_dir(), "spec/fixtures not present")
    def test_US2_AS5_every_real_writer_fixture_is_sent_and_graded(self):
        expected = len(list(REAL_FIXTURES.glob("*/*/rowStream.json")))
        self.assertGreater(expected, 10)
        self.timeout = "30"
        code, out = self.go("--caps", "writer", fixtures=REAL_FIXTURES)
        self.assertEqual(code, 0, out[-1500:])
        self.assertRegex(out, rf"(?m)^writer\s+{expected}\s+0\s+0$")

    @unittest.skipUnless(REAL_FIXTURES.is_dir(), "spec/fixtures not present")
    def test_the_whole_real_tree_with_both_capabilities_passes_and_lists_only_execution_equality(self):
        self.timeout = "30"
        code, out = self.go("--caps", "rejection,writer", fixtures=REAL_FIXTURES)
        self.assertEqual(code, 0, out[-1500:])
        listed = out.split("out of tier")[1] if "out of tier" in out else ""
        self.assertNotIn("rejection (SEC-6)", listed)
        self.assertNotIn("writer output", listed)


if __name__ == "__main__":
    unittest.main()
