#!/usr/bin/env python3
"""Pins scripts/check-dco.sh (story #1662, FR-02, AC-2): the DCO check of the public pull request workflow.

Scratch repositories only, no network. Needs bash and git; skips where one is missing. Each case builds a base commit and a few
pull request commits with scripted authors, committers and messages, then runs the script on `<base>..<head>`.
Run: python3 scripts/test_check_dco.py (also run by Craticula.Conformance.Tests on every `dotnet test`).
"""
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPT = HERE / "check-dco.sh"
NEED_TOOLS = unittest.skipUnless(all(shutil.which(t) for t in ("bash", "git")) and SCRIPT.exists(), "needs bash, git and the script")
ADA = ("Ada Lovelace", "ada@example.org")
GRACE = ("Grace Hopper", "grace@example.org")
BOT = ("github-actions[bot]", "41898282+github-actions[bot]@users.noreply.github.com")


def signed(person):
    return f"Signed-off-by: {person[0]} <{person[1]}>"


@NEED_TOOLS
class CheckDcoTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        config = self.tmp / "gitconfig"
        config.write_text("[user]\n\tname = Scratch\n\temail = scratch@example.invalid\n[init]\n\tdefaultBranch = main\n")
        self.env = {**os.environ, "GIT_CONFIG_GLOBAL": str(config), "GIT_CONFIG_NOSYSTEM": "1", "GIT_TERMINAL_PROMPT": "0"}
        self.repo = self.tmp / "repo"
        self.git("init", "-q", str(self.repo), cwd=self.tmp)
        self.counter = 0
        self.base = self.commit("the base, not signed off", ADA)

    def git(self, *args, cwd=None, check=True, env=None):
        done = subprocess.run(["git", *args], cwd=cwd or self.repo, env=env or self.env, capture_output=True, text=True)
        if check and done.returncode != 0:
            raise AssertionError(f"git {' '.join(args)} failed: {done.stdout}{done.stderr}")
        return done

    def commit(self, message, author=ADA, committer=None):
        self.counter += 1
        (self.repo / f"f{self.counter}.txt").write_text(f"{self.counter}\n")
        committer = committer or author
        env = {**self.env, "GIT_AUTHOR_NAME": author[0], "GIT_AUTHOR_EMAIL": author[1],
               "GIT_COMMITTER_NAME": committer[0], "GIT_COMMITTER_EMAIL": committer[1]}
        self.git("add", "-A", env=env)
        self.git("commit", "-q", "-m", message, env=env)
        return self.git("rev-parse", "HEAD").stdout.strip()

    def check(self, head=None, base=None, env_extra=None, summary=None):
        env = {**self.env, "DCO_REPO": str(self.repo), **(env_extra or {})}
        if summary:
            env["GITHUB_STEP_SUMMARY"] = str(summary)
        args = ["bash", str(SCRIPT), base or self.base, head or self.git("rev-parse", "HEAD").stdout.strip()]
        return subprocess.run(args, env=env, capture_output=True, text=True)

    def test_every_commit_signed_passes(self):
        self.commit(f"feat: one\n\n{signed(ADA)}")
        self.commit(f"fix: two\n\n{signed(ADA)}")
        done = self.check()
        self.assertEqual(0, done.returncode, done.stdout + done.stderr)
        self.assertIn("2 commit(s) signed off", done.stdout)

    def test_one_unsigned_commit_fails_and_only_it_is_named(self):
        self.commit(f"feat: good one\n\n{signed(ADA)}")
        bad = self.commit("fix: forgot the sign-off")
        self.commit(f"feat: good two\n\n{signed(ADA)}")
        done = self.check()
        self.assertEqual(1, done.returncode)
        self.assertIn("1 of 3 commit(s)", done.stdout)
        self.assertIn(f"{bad[:7]} fix: forgot the sign-off", done.stdout)
        self.assertNotIn("good one", done.stdout)
        self.assertNotIn("good two", done.stdout)
        self.assertIn("git commit --amend -s", done.stdout)
        self.assertIn(f"git rebase --signoff {self.base}", done.stdout)

    def test_every_unsigned_commit_is_listed(self):
        a = self.commit("fix: first bad")
        b = self.commit("fix: second bad")
        done = self.check()
        self.assertEqual(1, done.returncode)
        self.assertIn(a[:7], done.stdout)
        self.assertIn(b[:7], done.stdout)
        self.assertIn("2 of 2", done.stdout)

    def test_someone_elses_signoff_fails(self):
        self.commit(f"fix: x\n\n{signed(GRACE)}", ADA)
        done = self.check()
        self.assertEqual(1, done.returncode)
        self.assertIn("ada@example.org", done.stdout)

    def test_a_signoff_in_prose_does_not_count(self):
        self.commit(f"fix: x\n\n{signed(ADA)}\n\nand some prose after it, so it is not a trailer\n")
        self.assertEqual(1, self.check().returncode)

    def test_a_malformed_signoff_does_not_count(self):
        self.commit("fix: x\n\nSigned-off-by: Ada Lovelace")
        self.assertEqual(1, self.check().returncode)
        self.commit("fix: y\n\nSigned-off-by: <ada@example.org>")
        self.assertEqual(1, self.check().returncode)

    def test_the_email_is_compared_without_case(self):
        self.commit("fix: x\n\nSigned-off-by: Ada <ADA@Example.ORG>")
        self.assertEqual(0, self.check().returncode)

    def test_the_committers_signoff_is_accepted(self):
        """A commit rebased or cherry-picked by somebody else: the committer signs."""
        self.commit(f"fix: x\n\n{signed(GRACE)}", author=ADA, committer=GRACE)
        self.assertEqual(0, self.check().returncode)

    def test_a_co_signed_squash_message_passes_when_the_author_signed(self):
        self.commit(f"fix: x\n\n{signed(ADA)}\n{signed(GRACE)}")
        self.assertEqual(0, self.check().returncode)

    def test_crlf_messages_are_read(self):
        self.commit(f"fix: x\r\n\r\n{signed(ADA)}\r\n")
        self.assertEqual(0, self.check().returncode)

    def test_a_horizontal_rule_in_the_message_does_not_hide_the_signoff(self):
        self.commit(f"fix: x\n\nabove\n\n---\n\nbelow\n\n{signed(ADA)}")
        self.assertEqual(0, self.check().returncode)

    def test_merge_commits_are_exempt(self):
        main = self.git("rev-parse", "HEAD").stdout.strip()
        self.git("switch", "-q", "-c", "side")
        self.commit(f"fix: side\n\n{signed(ADA)}")
        self.git("switch", "-q", "main")
        self.commit(f"fix: main\n\n{signed(ADA)}")
        self.git("merge", "-q", "--no-ff", "-m", "Merge side into main", "side")
        done = self.check(base=main)
        self.assertEqual(0, done.returncode, done.stdout + done.stderr)
        self.assertIn("2 commit(s) signed off (1 merge commit(s)", done.stdout)

    def tree_of(self, rev):
        return self.git("rev-parse", f"{rev}^{{tree}}").stdout.strip()

    def crafted_merge(self, message, extra_file=True):
        """A merge made with commit-tree whose tree adds a file that neither parent has: content of its own."""
        main = self.git("rev-parse", "HEAD").stdout.strip()
        self.git("switch", "-q", "-c", "side")
        side = self.commit(f"fix: side\n\n{signed(ADA)}")
        self.git("switch", "-q", "main")
        if extra_file:
            (self.repo / "smuggled.txt").write_text("not in either parent\n")
            self.git("add", "-A")
            tree = self.git("write-tree").stdout.strip()
            self.git("reset", "-q", "--hard", main)
        else:
            tree = self.tree_of(main)
        env = {**self.env, "GIT_AUTHOR_NAME": ADA[0], "GIT_AUTHOR_EMAIL": ADA[1], "GIT_COMMITTER_NAME": ADA[0],
               "GIT_COMMITTER_EMAIL": ADA[1]}
        merge = self.git("commit-tree", tree, "-p", main, "-p", side, "-m", message, env=env).stdout.strip()
        return main, merge

    def test_a_merge_with_content_of_its_own_and_no_signoff_fails(self):
        base, merge = self.crafted_merge("Merge side, with a smuggled file")
        done = self.check(head=merge, base=base)
        self.assertEqual(1, done.returncode, done.stdout + done.stderr)
        self.assertIn(merge[:7], done.stdout)

    def test_a_merge_with_content_of_its_own_passes_when_signed_off(self):
        base, merge = self.crafted_merge(f"Merge side, with a file\n\n{signed(ADA)}")
        done = self.check(head=merge, base=base)
        self.assertEqual(0, done.returncode, done.stdout + done.stderr)

    def test_a_merge_that_only_combines_the_parents_is_exempt(self):
        base, merge = self.crafted_merge("Merge side", extra_file=False)
        done = self.check(head=merge, base=base)
        self.assertEqual(0, done.returncode, done.stdout + done.stderr)
        self.assertIn("1 merge commit(s)", done.stdout)

    def test_commits_already_in_the_base_are_ignored(self):
        self.commit("old: unsigned but already merged")
        base = self.git("rev-parse", "HEAD").stdout.strip()
        self.commit(f"fix: new\n\n{signed(ADA)}")
        self.assertEqual(0, self.check(base=base).returncode)

    def test_an_empty_range_passes(self):
        done = self.check(head=self.base)
        self.assertEqual(0, done.returncode)
        self.assertIn("0 commit(s)", done.stdout)

    def test_a_bot_author_email_is_not_an_exemption(self):
        """Anyone can write that e-mail into a commit."""
        self.commit("fix: pretends to be a bot", BOT)
        done = self.check()
        self.assertEqual(1, done.returncode)
        self.assertIn("pretends to be a bot", done.stdout)

    def test_the_exemption_comes_only_from_the_environment(self):
        self.commit("chore: release 1.2.3", BOT)
        done = self.check(env_extra={"DCO_EXEMPT": "pull request opened by Dependabot (dependabot[bot])"})
        self.assertEqual(0, done.returncode)
        self.assertIn("DCO check skipped: pull request opened by Dependabot", done.stdout)
        self.assertEqual(1, self.check(env_extra={"DCO_EXEMPT": ""}).returncode)

    def test_the_report_goes_to_the_job_summary_too(self):
        self.commit("fix: no sign-off")
        summary = self.tmp / "summary.md"
        self.assertEqual(1, self.check(summary=summary).returncode)
        self.assertIn("DCO check failed", summary.read_text())

    def raw_commit(self, author_line, subject):
        """A commit written with hash-object, so that the author line can hold what `git commit` would refuse."""
        tree = self.git("rev-parse", "HEAD^{tree}").stdout.strip()
        parent = self.git("rev-parse", "HEAD").stdout.strip()
        body = f"tree {tree}\nparent {parent}\nauthor {author_line}\ncommitter Scratch <scratch@example.invalid> 1700000000 +0000\n\n{subject}\n"
        done = subprocess.run(["git", "hash-object", "-t", "commit", "-w", "--stdin", "--literally"], cwd=self.repo, env=self.env,
                              input=body, capture_output=True, text=True, check=True)
        return done.stdout.strip()

    def test_commit_text_cannot_fake_a_workflow_command_or_a_line(self):
        head = self.raw_commit("Mallory <mallory@example.org\r::error::injected> 1700000000 +0000", "::set-output name=x::y")
        done = self.check(head=head)
        self.assertEqual(1, done.returncode)
        self.assertNotIn("\r", done.stdout)
        self.assertFalse([line for line in done.stdout.splitlines() if line.lstrip().startswith("::")], done.stdout)
        self.assertIn(head[:7], done.stdout)

    def test_a_backtick_in_a_subject_cannot_close_the_summary_fence(self):
        self.commit("fix: ``` break out of the fence")
        summary = self.tmp / "summary.md"
        self.assertEqual(1, self.check(summary=summary).returncode)
        inside = summary.read_text().split("```")
        self.assertEqual(3, len(inside), "exactly one fenced block")
        self.assertIn("break out of the fence", inside[1])

    def test_bad_arguments_are_a_usage_error(self):
        env = {**self.env, "DCO_REPO": str(self.repo)}
        for args in ([], ["a" * 40], ["main", "HEAD"], ["--help", "x"], ["a" * 40, "b" * 40, "c" * 40], ["a" * 39, "b" * 40]):
            with self.subTest(args=args):
                done = subprocess.run(["bash", str(SCRIPT), *args], env=env, capture_output=True, text=True)
                self.assertEqual(2, done.returncode, done.stdout + done.stderr)

    def test_a_commit_missing_from_the_clone_is_a_clear_error(self):
        done = self.check(head="b" * 40)
        self.assertEqual(2, done.returncode)
        self.assertIn("not in this clone", done.stderr)


WORKFLOW = HERE.parent / ".github" / "workflows" / "dco.yml"


def workflow_script(step_name):
    """The shell text of the `run: |` of the step called `step_name` (stdlib line scan)."""
    lines = WORKFLOW.read_text(encoding="utf-8").splitlines()
    named = next(n for n, line in enumerate(lines) if line.strip() == f"- name: {step_name}")
    start = next(n for n in range(named, len(lines)) if lines[n].strip() == "run: |")
    indent = len(lines[start]) - len(lines[start].lstrip(" "))
    body = []
    for line in lines[start + 1:]:
        if line.strip() and len(line) - len(line.lstrip(" ")) <= indent:
            break
        body.append(line[indent + 2:] if line.strip() else "")
    return "\n".join(body) + "\n"


@unittest.skipUnless(shutil.which("bash") and shutil.which("git") and WORKFLOW.exists(), "needs bash, git and the workflow")
class WorkflowTests(unittest.TestCase):
    """dco.yml: the exemption (the pull request author's login, head repository equal to this repository) and the data fetch."""
    REPO = "pluries/craticula"

    def exempt(self, author, head_repo, repository=REPO):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "scripts").mkdir()
            (root / "scripts" / "check-dco.sh").write_text('echo "EXEMPT=[${DCO_EXEMPT:-}] ARGS=[$1 $2]"\n')
            (root / "run.sh").write_text(workflow_script("Signed-off-by on every commit"))
            env = {**os.environ, "BASE_SHA": "a" * 40, "HEAD_SHA": "b" * 40, "PR_AUTHOR": author, "PR_HEAD_REPO": head_repo,
                   "GITHUB_REPOSITORY": repository}
            done = subprocess.run(["bash", "run.sh"], cwd=root, env=env, capture_output=True, text=True)
            self.assertEqual(0, done.returncode, done.stdout + done.stderr)
            return done.stdout

    def test_the_dependabot_pull_requests_of_this_repository_are_exempt(self):
        self.assertIn("EXEMPT=[pull request opened by Dependabot (dependabot[bot])]", self.exempt("dependabot[bot]", self.REPO))

    def test_the_shas_reach_the_script(self):
        self.assertIn(f"ARGS=[{'a' * 40} {'b' * 40}]", self.exempt("someone", self.REPO))

    def test_nobody_else_is_exempt(self):
        for author in ("someone", "github-actions[bot]", "github-actions[bot]x", "xgithub-actions[bot]", "github-actions", "dependabot", "Github-Actions[bot]", ""):
            with self.subTest(author=author):
                self.assertIn("EXEMPT=[]", self.exempt(author, self.REPO))

    def test_a_pull_request_from_another_repository_is_never_exempt(self):
        for head_repo in ("someone/craticula", "pluries/craticula-fork", "xpluries/craticula", "", "null"):
            with self.subTest(head_repo=head_repo):
                self.assertIn("EXEMPT=[]", self.exempt("github-actions[bot]", head_repo))
                self.assertIn("EXEMPT=[]", self.exempt("dependabot[bot]", head_repo))

    def test_an_empty_repository_variable_never_matches_an_empty_head(self):
        self.assertIn("EXEMPT=[]", self.exempt("github-actions[bot]", "", repository=""))

    def test_the_fetch_step_stops_when_the_head_moved(self):
        """The fetched head must be the commit the event named; run against a scratch 'origin' with a pull ref."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            env = {**os.environ, "GIT_CONFIG_GLOBAL": str(root / "gitconfig"), "GIT_CONFIG_NOSYSTEM": "1"}
            (root / "gitconfig").write_text("[user]\n\tname = S\n\temail = s@example.invalid\n[init]\n\tdefaultBranch = main\n")
            run = lambda *a, cwd=root: subprocess.run(list(a), cwd=cwd, env=env, capture_output=True, text=True, check=True)
            run("git", "init", "-q", "--bare", "origin.git")
            run("git", "clone", "-q", "origin.git", "work")
            work = root / "work"
            (work / "f").write_text("1\n")
            run("git", "add", "-A", cwd=work)
            run("git", "commit", "-q", "-m", "one", cwd=work)
            run("git", "push", "-q", "origin", "HEAD:refs/pull/7/head", cwd=work)
            head = run("git", "rev-parse", "HEAD", cwd=work).stdout.strip()
            script = root / "fetch.sh"
            script.write_text(workflow_script("Fetch the pull request commits"))
            for expected, code in ((head, 0), ("c" * 40, 1)):
                done = subprocess.run(["bash", str(script)], cwd=work, env={**env, "PR_NUMBER": "7", "HEAD_SHA": expected},
                                      capture_output=True, text=True)
                self.assertEqual(code, done.returncode, done.stdout + done.stderr)
            self.assertEqual(head, run("git", "rev-parse", "refs/dco/pr-head", cwd=work).stdout.strip())
            self.assertIn("moved", done.stdout)


if __name__ == "__main__":
    unittest.main()
