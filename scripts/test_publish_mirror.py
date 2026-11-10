#!/usr/bin/env python3
"""Pins the private-to-public mirror (scripts/publish_mirror.py and the publish and sync scripts), story #1659.

Scratch repositories and a scratch bare remote only: the real `github` remote is never contacted. The pure tests (message
mapping) always run; the script tests need bash, git, git-filter-repo and node, the scripts absent
from the public mirror and the secret-pattern detector (SECRET_PATTERNS_JS names it; else it is looked up under the
repository root), and skip where one is missing. Run: python3 scripts/test_publish_mirror.py
(also run by Craticula.Conformance.Tests/PublishMirrorTests.cs on every `dotnet test`).
"""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
import publish_mirror as mirror  # noqa: E402


def _find_secret_patterns():
    given = os.environ.get("SECRET_PATTERNS_JS")
    if given:
        return Path(given)
    found = sorted(ROOT.glob("*/skills/*/scripts/secret-patterns.js"))
    return found[0] if found else None


PUBLISH = HERE / "publish-github.sh"
SECRETS = _find_secret_patterns()
PROPS = "csharp/src/Directory.Build.props"
TOOLS = all(shutil.which(t) for t in ("bash", "git", "node")) and subprocess.run(
    ["git", "filter-repo", "--version"], capture_output=True).returncode == 0
NEED_SCRIPTS = unittest.skipUnless(
    TOOLS and PUBLISH.exists() and SECRETS is not None and SECRETS.exists(),
    "needs bash, git, git-filter-repo, node, the scripts absent from the public mirror and the secret-pattern detector")


class MappingTests(unittest.TestCase):
    def test_subject_mapping_table(self):
        table = [
            (b"FEATURE #12 add leave filter\n", b"feat: add leave filter (#12)\n"),
            (b"FIX #7 null payroll\n", b"fix: null payroll (#7)\n"),
            (b"TECHNICAL #1650 close the session records\n", b"chore: close the session records (#1650)\n"),
            (b"Merge #1658: NuGet packaging, pack smoke\n", b"chore: merge NuGet packaging, pack smoke (#1658)\n"),
            (b"FEATURE #3 add x\n\nBody line.\n\nBREAKING CHANGE: drops y\n", b"feat: add x (#3)\n\nBody line.\n\nBREAKING CHANGE: drops y\n"),
            (b"FIX #4 a  \n", b"fix: a (#4)\n"),
            (b"FIX #4 no trailing newline", b"fix: no trailing newline (#4)"),
            # no match: unchanged
            (b"#1649: add shared envelope mapping\n", b"#1649: add shared envelope mapping\n"),
            (b"feat: already conventional\n", b"feat: already conventional\n"),
            (b"Initial commit\n", b"Initial commit\n"),
            (b"FEATURE add without id\n", b"FEATURE add without id\n"),
            (b"Merge branch 'x'\n", b"Merge branch 'x'\n"),
            (b"", b""),
        ]
        for before, after in table:
            with self.subTest(before=before):
                self.assertEqual(mirror.map_message(before), after)

    def test_frozen_commits_keep_their_message(self):
        with tempfile.TemporaryDirectory() as tmp:
            frozen = Path(tmp) / "frozen.txt"
            frozen.write_text("a" * 40 + "\n")
            self.assertEqual(mirror.map_unless_frozen(b"a" * 40, b"FIX #1 x\n", str(frozen)), b"FIX #1 x\n")
            self.assertEqual(mirror.map_unless_frozen(b"b" * 40, b"FIX #1 x\n", str(frozen)), b"fix: x (#1)\n")


class DropPrivateChangesTests(unittest.TestCase):
    """#1665, ADR 0004: `docs` stays private except `docs/adr`, which is published only from the commits after a boundary."""

    class Change:
        def __init__(self, filename, type=b"M", mode=b"100644"):
            self.filename = filename
            self.type = type
            self.mode = mode

    class Commit:
        def __init__(self, original_id, names, changes=None):
            self.original_id = original_id
            self.file_changes = changes if changes is not None else [DropPrivateChangesTests.Change(n) for n in names]

        def names(self):
            return [c.filename for c in self.file_changes]

    NAMES = [b"README.md", b"docs/d.md", b"docs/adr/0001-x.md", b"docs/adrx/y.md", b"docs/adr", b"csharp/docs/z.md", b"site/site.json"]

    def frozen_file(self, *ids):
        path = Path(tempfile.mkdtemp()) / "frozen.txt"
        self.addCleanup(shutil.rmtree, path.parent, ignore_errors=True)
        path.write_bytes(b"".join(i + b"\n" for i in ids))
        return str(path)

    def test_after_the_boundary_only_the_adr_folder_survives_under_docs(self):
        commit = self.Commit(b"new", self.NAMES)
        mirror.drop_private_changes(commit, self.frozen_file(b"old"), ["docs"], ["docs/adr"])
        self.assertEqual([b"README.md", b"docs/adr/0001-x.md", b"csharp/docs/z.md", b"site/site.json"], commit.names())

    def test_at_or_before_the_boundary_nothing_under_docs_survives_as_before(self):
        commit = self.Commit(b"old", self.NAMES)
        mirror.drop_private_changes(commit, self.frozen_file(b"old"), ["docs"], ["docs/adr"])
        self.assertEqual([b"README.md", b"csharp/docs/z.md", b"site/site.json"], commit.names())

    def test_a_sibling_that_only_shares_the_prefix_is_not_the_exception(self):
        commit = self.Commit(b"new", [b"docs/adrx/y.md", b"docs/adr-old/z.md"])
        mirror.drop_private_changes(commit, self.frozen_file(), ["docs"], ["docs/adr"])
        self.assertEqual([], commit.names())

    def test_a_deletion_under_the_exception_is_kept_too(self):
        commit = self.Commit(b"new", [b"docs/adr/0001-x.md"])
        mirror.drop_private_changes(commit, self.frozen_file(b"old"), ["docs"], ["docs/adr"])
        self.assertEqual([b"docs/adr/0001-x.md"], commit.names())

    def test_a_root_file_named_like_the_private_folder_is_dropped_as_the_path_filter_did(self):
        commit = self.Commit(b"new", [b"docs", b"README.md"])
        mirror.drop_private_changes(commit, self.frozen_file(), ["docs"], ["docs/adr"])
        self.assertEqual([b"README.md"], commit.names())

    def test_a_symlink_or_a_submodule_under_the_exception_is_not_published_but_its_deletion_is(self):
        changes = [self.Change(b"docs/adr/link.md", mode=b"120000"), self.Change(b"docs/adr/sub", mode=b"160000"),
                   self.Change(b"docs/adr/run.md", mode=b"100755"), self.Change(b"docs/adr/gone.md", type=b"D", mode=None)]
        commit = self.Commit(b"new", None, changes)
        mirror.drop_private_changes(commit, self.frozen_file(), ["docs"], ["docs/adr"])
        self.assertEqual([b"docs/adr/run.md", b"docs/adr/gone.md"], commit.names())


def run(cwd, *cmd, env=None, check=True):
    result = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True)
    if check and result.returncode != 0:
        raise AssertionError(f"{' '.join(map(str, cmd))} exited {result.returncode}\n{result.stdout}\n{result.stderr}")
    return result


@NEED_SCRIPTS
class ScriptTests(unittest.TestCase):
    CLOCK = 1_700_000_000

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        config = self.tmp / "gitconfig"
        config.write_text("[user]\n\tname = Scratch Maker\n\temail = maker@example.invalid\n[init]\n\tdefaultBranch = main\n")
        self.env = {**os.environ, "GIT_CONFIG_GLOBAL": str(config), "GIT_CONFIG_NOSYSTEM": "1", "GIT_TERMINAL_PROMPT": "0"}
        self.priv = self.tmp / "priv"
        self.pub = self.tmp / "public.git"
        self.origin = self.tmp / "origin.git"
        run(self.tmp, "git", "init", "-q", str(self.priv), env=self.env)
        run(self.tmp, "git", "init", "-q", "--bare", str(self.pub), env=self.env)
        run(self.tmp, "git", "init", "-q", "--bare", str(self.origin), env=self.env)
        run(self.pub, "git", "config", "receive.denyNonFastForwards", "true", env=self.env)   # a force push would fail
        self.git("remote", "add", "origin", str(self.origin))
        self.write(".claude/rules.md", "private\n")
        self.write("docs/d.md", "private\n")
        self.write("site/site.json", "{}\n")      # the docs site is public (task #2836); docs/ above is not
        self.write("README.md", "# scratch\n")
        self.write(PROPS, "<Project><PropertyGroup>\n<Version>1.0.0</Version>\n</PropertyGroup></Project>\n")
        self.commit("Initial commit")
        self.write("a.txt", "a\n")
        self.boundary = self.commit("TECHNICAL #1 the published boundary")
        self.adr_after = self.boundary       # docs/adr is published from the commits after this one (ADR 0004)
        self.git("push", "-q", "origin", "main")

    def git(self, *args, cwd=None, check=True):
        return run(cwd or self.priv, "git", *args, env=self.env, check=check)

    def write(self, rel, text, root=None):
        path = (root or self.priv) / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)

    def commit(self, message, root=None):
        """Commits carry a scripted clock, one minute apart, so the history order is deterministic."""
        root = root or self.priv
        ScriptTests.CLOCK += 60
        stamp = f"{ScriptTests.CLOCK} +0000"
        env = {**self.env, "GIT_AUTHOR_DATE": stamp, "GIT_COMMITTER_DATE": stamp}
        self.git("add", "-A", cwd=root)
        run(root, "git", "commit", "-q", "-m", message, env=env)
        return self.git("rev-parse", "HEAD", cwd=root).stdout.strip()

    def publish(self, check=True, dry=False):
        env = {**self.env, "SRC": str(self.priv), "PUBLIC_REMOTE": str(self.pub), "PUBLISH_BOUNDARY": self.boundary,
               "SECRET_PATTERNS_JS": str(SECRETS), "PUBLISH_DRY_RUN": "1" if dry else "0", "PUBLISH_ADR_AFTER": self.adr_after}
        return run(self.priv, "bash", str(PUBLISH), env=env, check=check)

    def public_tip(self):
        return self.git("rev-parse", "main", cwd=self.pub).stdout.strip()

    def public_subjects(self, rev="main"):
        return self.git("log", "--topo-order", "--format=%s", rev, cwd=self.pub).stdout.splitlines()

    def public_clone(self):
        work = self.tmp / "work"
        if work.exists():
            shutil.rmtree(work)
        self.git("clone", "-q", str(self.pub), str(work), cwd=self.tmp)
        return work

    def public_commit(self, path, text, message="docs: public fix"):
        work = self.public_clone()
        self.write(path, text, root=work)
        sha = self.commit(message, root=work)
        self.git("push", "-q", "origin", "HEAD:refs/heads/main", cwd=work)
        return sha

    def assert_fast_forward(self, before_tip):
        tip = self.public_tip()
        self.assertNotEqual(tip, before_tip)
        self.assertTrue(mirror._is_ancestor(str(self.pub), before_tip, tip))
        return tip

    def test_published_history_keeps_its_hashes_and_later_commits_are_mapped(self):
        first = self.publish()
        self.assertIn("published", first.stdout)
        boundary_public = self.public_tip()
        self.assertEqual(self.public_subjects(), ["TECHNICAL #1 the published boundary", "Initial commit"])
        self.assertEqual(self.git("ls-tree", "-r", "--name-only", "main", cwd=self.pub).stdout.split(),
                         ["README.md", "a.txt", PROPS, "site/site.json"])    # site/ is public; no .claude, no docs

        self.write("b.txt", "b\n")
        self.commit("FEATURE #2 add thing\n\nBREAKING CHANGE: changes the shape")
        self.write("c.txt", "c\n")
        self.commit("FIX #3 repair thing")
        self.write("d.txt", "d\n")
        self.commit("TECHNICAL #4 tidy")
        self.publish()                                               # the bare remote refuses anything but a fast-forward
        self.assertTrue(mirror._is_ancestor(str(self.pub), boundary_public, "main"))   # the first publish's hashes survive
        self.assertEqual(self.public_subjects()[:3], ["chore: tidy (#4)", "fix: repair thing (#3)", "feat: add thing (#2)"])
        self.assertEqual(self.public_subjects()[3:], ["TECHNICAL #1 the published boundary", "Initial commit"])
        self.assertIn("BREAKING CHANGE: changes the shape", self.git("log", "-1", "--format=%B", "main~2", cwd=self.pub).stdout)

    def test_the_jenkins_files_stay_out_of_the_public_history(self):
        self.write("Jenkinsfile", "pipeline {}\n")
        self.write("jenkins/x", "private\n")
        self.commit("TECHNICAL #5 add the pipeline definition")
        self.publish()
        tree = self.git("ls-tree", "-r", "--name-only", "main", cwd=self.pub).stdout.split()
        self.assertNotIn("Jenkinsfile", tree)
        self.assertEqual([], [path for path in tree if path.startswith("jenkins")])

    def test_the_jenkins_drift_guard_and_its_wrapper_stay_out_of_the_public_history(self):
        # #3229: they pin private hosts, so they go with the Jenkinsfile; a neighbour of the wrapper stays public.
        self.write("scripts/test_jenkinsfile.py", "DTRACK_API = 'private host'\n")
        self.write("csharp/tests/Craticula.Conformance.Tests/JenkinsfileTests.cs", "// wrapper\n")
        self.write("csharp/tests/Craticula.Conformance.Tests/PublicTests.cs", "// stays\n")
        self.commit("TECHNICAL #6 add the pipeline guard")
        self.publish()
        tree = self.git("ls-tree", "-r", "--name-only", "main", cwd=self.pub).stdout.split()
        self.assertNotIn("scripts/test_jenkinsfile.py", tree)
        self.assertNotIn("csharp/tests/Craticula.Conformance.Tests/JenkinsfileTests.cs", tree)
        self.assertIn("csharp/tests/Craticula.Conformance.Tests/PublicTests.cs", tree)

    def test_the_release_steps_test_and_its_fixtures_stay_out_of_the_public_history(self):
        # #3485: they test jenkins/release-steps.sh, which is private, so in the public tree every test would error.
        self.write("scripts/test_release_steps.py", "# tests a private script\n")
        self.write("scripts/release-steps-fixtures/dotnet", "#!/usr/bin/env python3\n")
        self.write("scripts/test_release_verify.py", "# stays\n")
        self.write("csharp/tests/Craticula.Conformance.Tests/ReleaseStepsTests.cs", "// wrapper of the private tests\n")
        self.write("csharp/tests/Craticula.Conformance.Tests/ReleaseScriptsTests.cs", "// wrapper of the public tests\n")
        self.commit("TECHNICAL #7 add the release steps tests")
        self.publish()
        tree = self.git("ls-tree", "-r", "--name-only", "main", cwd=self.pub).stdout.split()
        self.assertNotIn("scripts/test_release_steps.py", tree)
        self.assertEqual([], [path for path in tree if path.startswith("scripts/release-steps-fixtures")])
        self.assertIn("scripts/test_release_verify.py", tree)
        self.assertNotIn("csharp/tests/Craticula.Conformance.Tests/ReleaseStepsTests.cs", tree)
        self.assertIn("csharp/tests/Craticula.Conformance.Tests/ReleaseScriptsTests.cs", tree)

    def test_the_release_certificate_file_reaches_the_public_history_and_the_release_job_files_do_not(self):
        # #3488, FR-33: the fingerprint is public; the job definition and its Jenkinsfile are private
        self.write("scripts/release-certificate.json", '{"sha256": "", "validUntil": "", "subject": ""}\n')
        self.write("jenkins/release.Jenkinsfile", "// private\n")
        self.write("jenkins/jobs/craticula-release.xml", "<flow-definition/>\n")
        self.commit("TECHNICAL #7 add the release job files")
        self.publish()
        tree = self.git("ls-tree", "-r", "--name-only", "main", cwd=self.pub).stdout.split()
        self.assertIn("scripts/release-certificate.json", tree)
        self.assertEqual([], [path for path in tree if path.startswith("jenkins/")])

    def test_the_release_publish_test_stays_out_of_the_public_history(self):
        # #3486: it tests the push and release commands of jenkins/release-steps.sh, which is private, like its sibling test.
        self.write("scripts/test_release_steps_publish.py", "# tests a private script\n")
        self.write("scripts/test_release_steps_notes.py", "# tests a private script\n")
        self.write("scripts/test_release_verify.py", "# stays\n")
        self.commit("TECHNICAL #7 add the release publish tests")
        self.publish()
        tree = self.git("ls-tree", "-r", "--name-only", "main", cwd=self.pub).stdout.split()
        self.assertNotIn("scripts/test_release_steps_publish.py", tree)
        self.assertNotIn("scripts/test_release_steps_notes.py", tree)
        self.assertIn("scripts/test_release_verify.py", tree)

    def public_tree(self):
        return self.git("ls-tree", "-r", "--name-only", "main", cwd=self.pub).stdout.split()

    def test_docs_adr_is_published_and_no_other_docs_path_is(self):
        # #1665 AC5 and AC6, ADR 0004: one commit adds an ADR and another document under docs/.
        self.write("docs/adr/0001-first.md", "# ADR 1\n\nClassification: Public\n")
        self.write("docs/other.md", "private\n")
        self.commit("TECHNICAL #6 add an adr and a private doc")
        self.publish()
        tree = self.public_tree()
        self.assertIn("docs/adr/0001-first.md", tree)
        self.assertEqual([], [path for path in tree if path.startswith("docs/") and not path.startswith("docs/adr/")])

    def test_an_adr_at_or_before_the_adr_boundary_enters_only_when_a_later_commit_touches_it(self):
        # The ADR exists in a commit that is already public (frozen): it stays out, as the plain filter kept it out, and the push
        # is still a fast-forward (the bare public remote refuses anything else). A later commit that edits it publishes the file.
        self.write("docs/adr/0002-old.md", "# ADR 2\n\nClassification: Public\n")
        self.adr_after = self.commit("TECHNICAL #7 an adr that is already public history")
        self.publish()
        self.assertNotIn("docs/adr/0002-old.md", self.public_tree())
        tip = self.public_tip()
        self.write("docs/adr/0002-old.md", "# ADR 2\n\nClassification: Public\n\nPublic now.\n")
        self.commit("TECHNICAL #8 touch the adr")
        self.publish()
        self.assertIn("docs/adr/0002-old.md", self.public_tree())
        self.assertTrue(mirror._is_ancestor(str(self.pub), tip, "main"))

    def test_a_record_not_marked_public_stops_the_publish_and_nothing_is_pushed(self):
        self.publish()
        before = self.public_tip()
        self.write("docs/adr/0003-draft.md", "# ADR 3\n\nClassification: Restricted\n\nNames an internal role.\n")
        self.commit("TECHNICAL #6 a draft record")
        result = self.publish(check=False)
        self.assertEqual(1, result.returncode)
        self.assertIn("not marked 'Classification: Public'", result.stdout + result.stderr)
        self.assertEqual(before, self.public_tip())

    def test_an_earlier_unmarked_version_of_a_record_stops_the_publish_even_if_the_latest_is_marked(self):
        # The unmarked version would stay public in the mirror's history, so the check reads every commit the publish brings in.
        self.publish()
        before = self.public_tip()
        self.write("docs/adr/0004-x.md", "# ADR 4\n\nClassification: Restricted\n")
        self.commit("TECHNICAL #6 first version")
        self.write("docs/adr/0004-x.md", "# ADR 4\n\nClassification: Public\n")
        self.commit("TECHNICAL #7 marked now")
        self.assertEqual(1, self.publish(check=False).returncode)
        self.assertEqual(before, self.public_tip())

    def test_a_file_under_docs_adr_that_is_not_markdown_stops_the_publish(self):
        self.publish()
        self.write("docs/adr/notes.txt", "Classification: Public\n")
        self.commit("TECHNICAL #6 a text file")
        self.assertEqual(1, self.publish(check=False).returncode)

    def test_a_commit_that_changes_only_another_docs_file_is_not_published_as_an_empty_commit(self):
        self.publish()
        self.write("docs/only-private.md", "private\n")
        self.commit("TECHNICAL #6 a private doc only")
        self.write("c.txt", "c\n")
        self.commit("FIX #7 a public change")
        self.publish()
        self.assertEqual(["fix: a public change (#7)", "TECHNICAL #1 the published boundary", "Initial commit"], self.public_subjects())

    def test_the_boundary_commit_must_be_in_the_history(self):
        self.adr_after = "0" * 40
        result = self.publish(check=False)
        self.assertNotEqual(0, result.returncode)
        self.assertIn("PUBLISH_ADR_AFTER", result.stdout + result.stderr)

    def test_merge_subjects_are_mapped(self):
        self.publish()
        self.git("checkout", "-q", "-b", "topic")
        self.write("t.txt", "t\n")
        self.commit("FEATURE #5 topic work")
        self.git("checkout", "-q", "main")
        self.git("merge", "--no-ff", "-q", "-m", "Merge #5: topic work", "topic")
        self.publish()
        subjects = self.public_subjects()
        self.assertEqual(subjects[:2], ["chore: merge topic work (#5)", "feat: topic work (#5)"])

    def test_probe_c_a_public_readme_fix_copied_with_a_trailer_does_not_block(self):
        self.publish()
        before = self.public_tip()
        fix = self.public_commit("README.md", "# scratch\nfixed on GitHub\n")
        blocked = self.publish(check=False)
        self.assertEqual(blocked.returncode, 1)
        self.assertIn(fix, blocked.stderr)
        self.assertIn("README.md", blocked.stderr)
        self.assertIn(f"Public-Sync: {fix}", blocked.stderr)
        self.write("README.md", "# scratch\nfixed on GitHub\n")
        self.commit(f"TECHNICAL #10 copy the public README fix\n\nPublic-Sync: {fix}")
        self.publish()
        tip = self.assert_fast_forward(before)
        self.assertEqual(self.git("show", f"{tip}:README.md", cwd=self.pub).stdout, "# scratch\nfixed on GitHub\n")
        self.publish()                                               # and the next round is accepted again

    def test_a_public_change_is_refused_until_private_records_it_then_the_publish_fast_forwards(self):
        self.publish()
        before = self.public_tip()
        self.write("b.txt", "b\n")
        self.commit("FEATURE #2 add thing")
        fix = self.public_commit("README.md", "# scratch\nfixed on GitHub\n")
        blocked = self.publish(check=False)
        self.assertEqual(blocked.returncode, 1)
        self.assertIn("is not recorded in private main", blocked.stderr)
        self.assertIn("scripts/apply-public-change.sh " + fix, blocked.stderr)
        self.assertEqual(self.public_tip(), fix)                     # nothing was pushed
        self.write("README.md", "# scratch\nfixed on GitHub\n")
        self.commit(f"TECHNICAL #10 copy the public README fix\n\nPublic-Sync: {fix}")
        dry = self.publish(dry=True)
        self.assertIn("merge commit over the public tip", dry.stdout)
        self.assertEqual(self.public_tip(), fix)                     # a dry run pushes nothing
        self.publish()
        tip = self.assert_fast_forward(before)
        parents = self.git("rev-list", "--parents", "-n", "1", tip, cwd=self.pub).stdout.split()[1:]
        self.assertEqual(len(parents), 2)
        self.assertEqual(parents[0], fix)                            # fast-forward over the public tip
        self.assertEqual(self.git("rev-parse", f"{tip}^{{tree}}", cwd=self.pub).stdout,
                         self.git("rev-parse", f"{parents[1]}^{{tree}}", cwd=self.pub).stdout)   # the filtered head's tree
        self.assertEqual(self.git("log", "-1", "--format=%B", tip, cwd=self.pub).stdout, mirror.MERGE_SUBJECT + "\n\n")
        again = self.publish()                                       # our own merge is accepted on the next round
        self.assertIn("nothing to publish", again.stdout)
        self.write("f.txt", "f\n")
        self.commit("FEATURE #7 next")
        self.publish()
        self.assertIn("feat: next (#7)", self.public_subjects())

    def test_an_empty_record_commit_keeps_its_trailer_so_the_publish_still_runs(self):
        # apply-public-change.sh may find the change already in private main and commit with --allow-empty; that commit carries the
        # Public-Sync trailer, so the filter must not prune it (an explicit --prune-empty always would, and the publish deadlocked).
        self.publish()
        fix = self.public_commit("README.md", "# scratch\nfixed on GitHub\n")
        self.write("README.md", "# scratch\nfixed on GitHub\n")
        self.commit("TECHNICAL #8 the same change, already in private")
        run(self.priv, "git", "commit", "--allow-empty", "-q", "-m", f"TECHNICAL #9 record the public fix\n\nPublic-Sync: {fix}", env=self.env)
        self.assertEqual(0, self.publish(check=False).returncode)

    def test_the_merge_message_is_a_plain_chore_subject(self):
        self.assertEqual(mirror.merge_message(), mirror.MERGE_SUBJECT + "\n")
        self.assertTrue(mirror.MERGE_SUBJECT.startswith("chore: "))

    def test_a_public_release_commit_is_refused_like_any_other_unrecorded_change(self):
        self.publish()
        work = self.public_clone()
        self.write(PROPS, "<Project/>\n", root=work)
        release = self.commit("chore: release dotnet 1.0.1", root=work)
        self.git("push", "-q", "origin", "HEAD:refs/heads/main", cwd=work)
        blocked = self.publish(check=False)
        self.assertEqual(blocked.returncode, 1)
        self.assertIn(release, blocked.stderr)
        self.assertIn(PROPS, blocked.stderr)

    def test_a_public_merge_touching_another_path_is_refused(self):
        self.publish()
        work = self.public_clone()
        self.git("checkout", "-q", "-b", "side", cwd=work)
        self.write("README.md", "# edited\n", root=work)
        side = self.commit("docs: edit", root=work)
        self.git("checkout", "-q", "main", cwd=work)
        self.write("x.txt", "x\n", root=work)
        self.commit("docs: x", root=work)
        run(work, "git", "merge", "--no-ff", "-q", "-m", "Merge side", "side", env=self.env)
        self.git("push", "-q", "origin", "HEAD:refs/heads/main", cwd=work)
        blocked = self.publish(check=False)
        self.assertEqual(blocked.returncode, 1)
        self.assertTrue("README.md" in blocked.stderr or "x.txt" in blocked.stderr)
        self.assertTrue(side in blocked.stderr or "touches" in blocked.stderr)


if __name__ == "__main__":
    unittest.main()
