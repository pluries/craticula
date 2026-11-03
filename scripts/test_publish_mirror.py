#!/usr/bin/env python3
"""Pins the private-to-public mirror (scripts/publish_mirror.py and the publish and sync scripts), story #1659.

Scratch repositories and a scratch bare remote only: the real `github` remote is never contacted. The pure tests (message
mapping, Release Please's rule) always run; the script tests need bash, git, git-filter-repo and node, the scripts absent
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
SYNC = HERE / "sync-release-commit.sh"
SECRETS = _find_secret_patterns()
PROPS = "csharp/src/Directory.Build.props"
TOOLS = all(shutil.which(t) for t in ("bash", "git", "node")) and subprocess.run(
    ["git", "filter-repo", "--version"], capture_output=True).returncode == 0
NEED_SCRIPTS = unittest.skipUnless(
    TOOLS and PUBLISH.exists() and SYNC.exists() and SECRETS is not None and SECRETS.exists(),
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

    def test_release_please_rule(self):
        table = [("feat: x (#1)", "minor"), ("fix: x (#1)", "patch"), ("feat!: x", "major"), ("fix(core)!: x", "major"),
                 ("feat: x\n\nBREAKING CHANGE: y", "major"), ("chore: merge x (#3)", None), ("docs: x", None),
                 ("Merge #3: x", None), ("FIX #3 x", None), ("chore: merge the private history into the public mirror", None),
                 # one message, several entries: split at a blank line followed by `type: ` (release-please splitMessages)
                 ("chore: merge\n\nfeat: a (#1)\n\nfix: b (#2)", "minor"),
                 ("chore: merge\n\nfix: b (#2)\n\nchore: c (#3)", "patch"),
                 ("chore: merge\n\nchore: c (#3)\n\ndocs: d", None),
                 ("chore: merge\n\nfeat: a (#1)\n\nBREAKING CHANGE: y\n\nfix: b", "major"),
                 # `!` is not in the split pattern: a `feat!:` paragraph stays inside the previous entry (the merge message
                 # therefore states a break as a footer, see publish_mirror.merge_message)
                 ("chore: merge\n\nfeat!: a (#1)", None),
                 # no blank line before the type: not split, so only the first line counts
                 ("chore: merge\nfeat: a (#1)", None)]
        for message, expected in table:
            with self.subTest(message=message):
                self.assertEqual(mirror.release_type(message), expected)

    def test_mapped_merge_commits_open_no_release(self):
        for subject in (b"Merge #1658: NuGet packaging\n", b"Merge #2: FEATURE-ish text\n"):
            self.assertIsNone(mirror.release_type(mirror.map_message(subject).decode()))
        self.assertEqual(mirror.release_type(mirror.map_message(b"FEATURE #5 add a thing\n").decode()), "minor")
        self.assertEqual(mirror.release_type(mirror.map_message(b"FIX #5 repair a thing\n").decode()), "patch")
        self.assertIsNone(mirror.release_type(mirror.map_message(b"TECHNICAL #5 tidy\n").decode()))


def run(cwd, *cmd, env=None, check=True):
    result = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True)
    if check and result.returncode != 0:
        raise AssertionError(f"{' '.join(map(str, cmd))} exited {result.returncode}\n{result.stdout}\n{result.stderr}")
    return result


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
        """Commits carry a scripted clock, one minute apart, so the date order Release Please walks is deterministic."""
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

    def sync(self, sha, check=True):
        env = {**self.env, "SRC": str(self.priv), "PUBLIC_REMOTE": str(self.pub)}
        return run(self.priv, "bash", str(SYNC), sha, "--work-item", "9", env=env, check=check)

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

    def release_commit(self, version, extra_path=None, props_suffix="", changelog=None, link=False, push=True, readme_edit=None):
        """What Release Please does on the public repository: bump the version, write the changelog and the manifest."""
        work = self.public_clone()
        props = (work / PROPS).read_text().replace("<Version>1.0.0</Version>", f"<Version>{version}</Version>")
        (work / PROPS).write_text(props.replace("</PropertyGroup>", props_suffix + "</PropertyGroup>"))
        if link:
            (work / "CHANGELOG.md").unlink(missing_ok=True)
            (work / "CHANGELOG.md").symlink_to("README.md")
        else:
            (work / "CHANGELOG.md").write_bytes(changelog if changelog is not None else f"# Changelog\n\n## {version}\n".encode())
        self.write(".release-please-manifest.json", f'{{".": "{version}"}}\n', root=work)
        if readme_edit:
            (work / "README.md").write_text(readme_edit((work / "README.md").read_text()))
        if extra_path:
            self.write(extra_path, "changed on the public side\n", root=work)
        sha = self.commit(f"chore: release dotnet {version}", root=work)
        if push:
            self.git("push", "-q", "origin", "HEAD:refs/heads/main", cwd=work)
        return sha

    def public_commit(self, path, text, message="docs: public fix"):
        work = self.public_clone()
        self.write(path, text, root=work)
        sha = self.commit(message, root=work)
        self.git("push", "-q", "origin", "HEAD:refs/heads/main", cwd=work)
        return sha

    def released_and_published(self, version="1.0.1"):
        """Publish, one feature, a public release commit, its sync, and the publish that follows (the merge commit)."""
        self.publish()
        self.write("b.txt", "b\n")
        self.commit("FEATURE #2 add thing")
        release = self.release_commit(version)
        self.sync(release)
        self.publish()
        return release

    MARKED = "Latest release: 1.0.0 <!-- x-release-please-version -->"
    README_WITH_MARKER = f"# scratch\n\nSpec 0.1.0 stays.\n\n{MARKED}\n\nMore text.\n"

    def published_with_marked_readme(self):
        """A private README with the marked line, published, plus one feature, so a release commit has something to release."""
        self.write("README.md", self.README_WITH_MARKER)
        self.commit("TECHNICAL #11 add the marked line")
        self.publish()
        self.write("b.txt", "b\n")
        self.commit("FEATURE #2 add thing")

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
        self.commit("TECHNICAL #7 add the release steps tests")
        self.publish()
        tree = self.git("ls-tree", "-r", "--name-only", "main", cwd=self.pub).stdout.split()
        self.assertNotIn("scripts/test_release_steps.py", tree)
        self.assertEqual([], [path for path in tree if path.startswith("scripts/release-steps-fixtures")])
        self.assertIn("scripts/test_release_verify.py", tree)

    def test_the_release_publish_test_stays_out_of_the_public_history(self):
        # #3486: it tests the push and release commands of jenkins/release-steps.sh, which is private, like its sibling test.
        self.write("scripts/test_release_steps_publish.py", "# tests a private script\n")
        self.write("scripts/test_release_verify.py", "# stays\n")
        self.commit("TECHNICAL #7 add the release publish tests")
        self.publish()
        tree = self.git("ls-tree", "-r", "--name-only", "main", cwd=self.pub).stdout.split()
        self.assertNotIn("scripts/test_release_steps_publish.py", tree)
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

    def test_an_empty_sync_commit_keeps_its_trailer_so_the_publish_still_runs(self):
        # sync-release-commit.sh commits with --allow-empty when private already holds the release files; that commit carries the
        # Public-Sync trailer, so the filter must not prune it (an explicit --prune-empty always would, and the publish deadlocked).
        self.publish()
        self.write("b.txt", "b\n")
        self.commit("FEATURE #2 add thing")
        release = self.release_commit("1.0.1")
        self.write(PROPS, "<Project><PropertyGroup>\n<Version>1.0.1</Version>\n</PropertyGroup></Project>\n")
        self.write("CHANGELOG.md", "# Changelog\n\n## 1.0.1\n")
        self.write(".release-please-manifest.json", '{".": "1.0.1"}\n')
        self.commit("TECHNICAL #8 the same release files, already in private")
        self.sync(release)                                            # nothing to copy: an empty commit with the trailer
        self.assertEqual("", self.git("diff", "--stat", "HEAD~1", "HEAD").stdout.strip())
        self.assertEqual(0, self.publish(check=False).returncode)

    def test_the_boundary_commit_must_be_in_the_history(self):
        self.adr_after = "0" * 40
        result = self.publish(check=False)
        self.assertNotEqual(0, result.returncode)
        self.assertIn("PUBLISH_ADR_AFTER", result.stdout + result.stderr)

    def test_merge_subjects_are_mapped_and_open_no_release(self):
        self.publish()
        self.git("checkout", "-q", "-b", "topic")
        self.write("t.txt", "t\n")
        self.commit("FEATURE #5 topic work")
        self.git("checkout", "-q", "main")
        self.git("merge", "--no-ff", "-q", "-m", "Merge #5: topic work", "topic")
        self.publish()
        subjects = self.public_subjects()
        self.assertEqual(subjects[:2], ["chore: merge topic work (#5)", "feat: topic work (#5)"])
        self.assertIsNone(mirror.release_type(subjects[0]))
        self.assertEqual(mirror.release_type(subjects[1]), "minor")    # the feature commit itself is what releases

    def test_sync_back_round_trip_ends_in_a_fast_forward(self):
        self.publish()
        before = self.public_tip()
        self.write("b.txt", "b\n")
        self.commit("FEATURE #2 add thing")
        release = self.release_commit("1.0.1")

        blocked = self.publish(check=False)                          # the release commit is not recorded in private main yet
        self.assertEqual(blocked.returncode, 1)
        self.assertIn("scripts/sync-release-commit.sh " + release, blocked.stderr)
        self.assertIn("is not recorded in private main", blocked.stderr)
        self.assertEqual(self.public_tip(), release)                 # nothing was pushed

        synced = self.sync(release)
        self.assertIn("sync release 1.0.1", synced.stdout)
        self.assertEqual(self.git("log", "-1", "--format=%s").stdout.strip(), "TECHNICAL #9 sync release 1.0.1")
        self.assertEqual(self.git("log", "-1", "--format=%(trailers:key=Public-Sync,valueonly)").stdout.strip(), release)
        self.assertEqual(self.sync(release).returncode, 0)           # idempotent: already in sync, no second commit
        self.assertEqual(self.git("rev-list", "--count", "HEAD").stdout.strip(), "4")
        self.write("e.txt", "e\n")
        self.commit("FIX #6 after the release")

        dry = self.publish(dry=True)
        self.assertIn("history secret scan: clean", dry.stdout)
        self.assertIn("merge commit over the public tip", dry.stdout)
        self.assertEqual(self.public_tip(), release)                 # a dry run pushes nothing

        self.publish()
        tip = self.public_tip()
        parents = self.git("rev-list", "--parents", "-n", "1", tip, cwd=self.pub).stdout.split()[1:]
        self.assertEqual(len(parents), 2)
        self.assertEqual(parents[0], release)                        # fast-forward over the public tip
        self.assertTrue(mirror._is_ancestor(str(self.pub), before, tip))
        self.assertEqual(self.git("rev-parse", f"{tip}^{{tree}}", cwd=self.pub).stdout,
                         self.git("rev-parse", f"{parents[1]}^{{tree}}", cwd=self.pub).stdout)   # the filtered head's tree
        self.assertEqual(self.git("show", f"{tip}:CHANGELOG.md", cwd=self.pub).stdout, "# Changelog\n\n## 1.0.1\n")
        self.assertIn("<Version>1.0.1</Version>", self.git("show", f"{tip}:{PROPS}", cwd=self.pub).stdout)
        self.assertEqual(self.public_subjects()[0], mirror.MERGE_SUBJECT)
        self.assertIsNone(mirror.release_type(self.public_subjects()[0]))

        # Our own merge is accepted on the next round, with new private work and with none.
        again = self.publish()
        self.assertIn("nothing to publish", again.stdout)
        self.write("f.txt", "f\n")
        self.commit("FEATURE #7 next")
        self.publish()
        self.assertIn("feat: next (#7)", self.public_subjects())
        self.assertEqual(self.public_subjects()[0], mirror.MERGE_SUBJECT)

    def test_merge_message_lists_the_commits_and_release_please_counts_them(self):
        self.publish()
        self.write("b.txt", "b\n")
        self.commit("FEATURE #2 add thing")
        self.write("t.txt", "t\n")
        self.commit("TECHNICAL #3 tidy")
        release = self.release_commit("1.0.1")
        self.sync(release)
        self.write("e.txt", "e\n")
        self.commit("FIX #6 after the release")        # dated after the release commit: Release Please counts it itself
        self.publish()
        message = self.git("log", "-1", "--format=%B", "main", cwd=self.pub).stdout
        self.assertEqual(message.split("\n")[0], mirror.MERGE_SUBJECT)
        self.assertEqual(message.strip().split("\n\n")[1:], ["feat: add thing (#2)", "chore: tidy (#3)"])   # strongest first
        self.assertEqual(mirror.release_type(message), "minor")        # the feature behind the merge opens a release

    def test_a_merge_bringing_only_chores_opens_no_release(self):
        self.publish()
        self.write("t.txt", "t\n")
        self.commit("TECHNICAL #3 tidy")
        self.write("u.txt", "u\n")
        self.commit("Merge #4: housekeeping")
        release = self.release_commit("1.0.1")
        self.sync(release)
        self.publish()
        message = self.git("log", "-1", "--format=%B", "main", cwd=self.pub).stdout
        self.assertIn("chore: tidy (#3)", message)
        self.assertIsNone(mirror.release_type(message))

    def test_merge_message_orders_by_strength_and_is_bounded(self):
        self.write("base.txt", "base\n")
        base = self.commit("TECHNICAL #1 base")
        for subject in ("chore: c1", "fix: f1", "feat: a1", "feat!: breaking one", "chore: c2",
                        "fix: f2\n\nBREAKING CHANGE: shape", "Merge branch 'x'", "#12: not conventional"):
            self.write("f.txt", subject)
            self.commit(subject)
        full = mirror.merge_message(str(self.priv), base, "HEAD")
        self.assertEqual(full.strip().split("\n\n"), [mirror.MERGE_SUBJECT, "fix: f2", "BREAKING CHANGE: shape", "feat: breaking one", "BREAKING CHANGE: breaking one",
                                                       "feat: a1", "fix: f1", "chore: c2", "chore: c1"])
        capped = mirror.merge_message(str(self.priv), base, "HEAD", cap=2)
        self.assertEqual(capped.strip().split("\n\n"), [mirror.MERGE_SUBJECT, "fix: f2", "BREAKING CHANGE: shape", "feat: breaking one", "BREAKING CHANGE: breaking one",
                                                         "... and 4 more commits not listed"])
        self.assertEqual(mirror.release_type(capped), "major")

    def test_a_foreign_public_change_is_refused(self):
        self.publish()
        self.write("b.txt", "b\n")
        self.commit("FEATURE #2 add thing")
        foreign = self.release_commit("1.0.1", extra_path="README.md")
        blocked = self.publish(check=False)
        self.assertEqual(blocked.returncode, 1)
        self.assertIn(foreign, blocked.stderr)
        self.assertIn("README.md", blocked.stderr)
        self.assertEqual(self.public_tip(), foreign)
        refused = self.sync(foreign, check=False)
        self.assertEqual(refused.returncode, 1)
        self.assertIn("README.md", refused.stderr)

    def test_sync_takes_the_readme_marker_line_and_the_next_publish_fast_forwards(self):
        self.published_with_marked_readme()
        before = self.public_tip()
        release = self.release_commit("1.0.1", readme_edit=lambda t: t.replace("Latest release: 1.0.0", "Latest release: 1.0.1"))
        synced = self.sync(release)
        self.assertIn("sync release 1.0.1", synced.stdout)
        self.assertIn("README.md", self.git("log", "-1", "--format=%B").stdout)
        self.assertEqual((self.priv / "README.md").read_text(), self.README_WITH_MARKER.replace("1.0.0", "1.0.1"))
        self.assertIn("<Version>1.0.1</Version>", (self.priv / PROPS).read_text())
        self.assertEqual((self.priv / ".release-please-manifest.json").read_text(), '{".": "1.0.1"}\n')
        self.assertEqual(self.git("log", "-1", "--format=%(trailers:key=Public-Sync,valueonly)").stdout.strip(), release)
        self.publish()                                               # the bare remote refuses anything but a fast-forward
        tip = self.assert_fast_forward(before)
        self.assertIn("Latest release: 1.0.1", self.git("show", f"{tip}:README.md", cwd=self.pub).stdout)
        self.assertIn("nothing to publish", self.publish().stdout)

    def test_sync_edits_only_the_marked_line_of_the_private_readme(self):
        self.published_with_marked_readme()
        release = self.release_commit("1.0.1", readme_edit=lambda t: t.replace("Latest release: 1.0.0", "Latest release: 1.0.1"))
        private = self.README_WITH_MARKER.replace("Spec 0.1.0 stays.", "Edited in private only.")
        self.write("README.md", private)
        self.commit("TECHNICAL #12 edit the README in private")
        self.sync(release)
        self.assertEqual((self.priv / "README.md").read_text(), private.replace("1.0.0", "1.0.1"))

    def test_a_readme_change_beyond_the_marked_line_is_refused(self):
        self.published_with_marked_readme()
        cases = {
            "an extra line": lambda t: t.replace("Latest release: 1.0.0", "Latest release: 1.0.1") + "Injected line.\n",
            "another line only": lambda t: t.replace("More text.", "Other text."),
            "marker line and another line": lambda t: t.replace("Latest release: 1.0.0", "Latest release: 1.0.1").replace("More text.", "Other text."),
            "text on the marked line": lambda t: t.replace("Latest release: 1.0.0", "Latest release: 1.0.1 and more"),
        }
        for name, edit in cases.items():
            with self.subTest(name):
                before = self.public_tip()
                foreign = self.release_commit("1.0.1", readme_edit=edit)
                blocked = self.publish(check=False)
                self.assertEqual(blocked.returncode, 1, blocked.stdout)
                self.assertIn(foreign, blocked.stderr)
                self.assertIn("README.md", blocked.stderr)
                self.assertEqual(self.public_tip(), foreign)
                refused = self.sync(foreign, check=False)
                self.assertEqual(refused.returncode, 1)
                self.assertIn("README.md", refused.stderr)
                self.assertEqual(self.git("status", "--porcelain", "--untracked-files=no").stdout, "")   # nothing was written
                run(self.pub, "git", "config", "receive.denyNonFastForwards", "false", env=self.env)
                run(self.pub, "git", "update-ref", "refs/heads/main", before, env=self.env)
                run(self.pub, "git", "config", "receive.denyNonFastForwards", "true", env=self.env)

    def test_a_marked_line_with_two_semvers_or_a_non_semver_is_refused(self):
        self.published_with_marked_readme()
        for name, new in {"two semvers": "Latest release: 1.0.1 and 1.0.2 <!-- x-release-please-version -->",
                          "not a semver": "Latest release: one-point-oh <!-- x-release-please-version -->",
                          "short version": "Latest release: 1.1 <!-- x-release-please-version -->",
                          "marker removed": "Latest release: 1.0.1"}.items():
            with self.subTest(name):
                before = self.public_tip()
                foreign = self.release_commit("1.0.1", readme_edit=lambda t, new=new: t.replace(self.MARKED, new))
                blocked = self.publish(check=False)
                self.assertEqual(blocked.returncode, 1, blocked.stdout)
                self.assertIn("README.md", blocked.stderr)
                self.assertIn(foreign, blocked.stderr)
                refused = self.sync(foreign, check=False)
                self.assertEqual(refused.returncode, 1)
                self.assertIn("README.md", refused.stderr)
                run(self.pub, "git", "config", "receive.denyNonFastForwards", "false", env=self.env)
                run(self.pub, "git", "update-ref", "refs/heads/main", before, env=self.env)
                run(self.pub, "git", "config", "receive.denyNonFastForwards", "true", env=self.env)

    def test_sync_refuses_a_marked_line_edited_in_private_since_the_public_parent(self):
        self.published_with_marked_readme()
        release = self.release_commit("1.0.2", readme_edit=lambda t: t.replace("Latest release: 1.0.0", "Latest release: 1.0.2"))
        self.write("README.md", self.README_WITH_MARKER.replace("1.0.0", "1.0.1"))
        self.commit("TECHNICAL #13 bump the marked line in private")
        refused = self.sync(release, check=False)
        self.assertEqual(refused.returncode, 1)
        self.assertIn("Latest release", refused.stderr)
        self.assertIn("merge it by hand", refused.stderr)

    def test_sync_refuses_a_dirty_tree_and_a_private_version_edit_it_would_overwrite(self):
        self.publish()
        release = self.release_commit("1.0.1")
        self.write(PROPS, "<Project><PropertyGroup>\n<Version>1.0.0</Version>\n<Other/>\n</PropertyGroup></Project>\n")
        self.assertIn("not clean", self.sync(release, check=False).stderr)
        self.git("checkout", "--", PROPS)
        self.write(PROPS, "<Project><PropertyGroup>\n<Version>1.0.5</Version>\n</PropertyGroup></Project>\n")
        self.commit("TECHNICAL #8 bump the version in private")
        refused = self.sync(release, check=False)
        self.assertEqual(refused.returncode, 1)
        self.assertIn("<Version>", refused.stderr)
        self.assertIn("merge it by hand", refused.stderr)

    def test_sync_leaves_a_private_edit_of_the_props_file_alone(self):
        self.publish()
        release = self.release_commit("1.0.1")
        self.write(PROPS, "<Project><PropertyGroup>\n<Version>1.0.0</Version>\n<Other/>\n</PropertyGroup></Project>\n")
        self.commit("TECHNICAL #8 edit the props in private")
        self.sync(release)
        self.assertEqual((self.priv / PROPS).read_text(),
                         "<Project><PropertyGroup>\n<Version>1.0.1</Version>\n<Other/>\n</PropertyGroup></Project>\n")

    def test_sync_takes_only_the_version_from_the_public_props_file(self):
        self.publish()
        release = self.release_commit("1.0.1", props_suffix="<Injected>$(Foo)</Injected>\n")
        refused = self.sync(release, check=False)
        self.assertEqual(refused.returncode, 1)
        self.assertIn("beyond the <Version> value", refused.stderr)
        self.assertIn("Injected", refused.stderr)
        self.assertEqual(self.git("status", "--porcelain", "--untracked-files=no").stdout, "")   # nothing was written

    def test_sync_refuses_a_changelog_with_a_nul_and_a_symlink(self):
        self.publish()
        nul = self.release_commit("1.0.1", changelog=b"# Changelog\n\x00\n")
        refused = self.sync(nul, check=False)
        self.assertEqual(refused.returncode, 1)
        self.assertIn("NUL", refused.stderr)
        self.assertEqual(self.git("status", "--porcelain", "--untracked-files=no").stdout, "")
        link = self.release_commit("1.0.1", link=True)
        refused = self.sync(link, check=False)
        self.assertEqual(refused.returncode, 1)
        self.assertIn("not a regular file", refused.stderr)

    def test_sync_runs_from_a_work_branch_that_contains_origin_main(self):
        self.publish()
        release = self.release_commit("1.0.1")
        self.git("checkout", "-q", "-b", "csn/9-sync-release")
        self.assertIn("sync release 1.0.1", self.sync(release).stdout)
        self.assertEqual(self.git("rev-parse", "--abbrev-ref", "HEAD").stdout.strip(), "csn/9-sync-release")

    def test_sync_refuses_a_head_that_lacks_origin_main(self):
        self.publish()
        release = self.release_commit("1.0.1")
        self.write("z.txt", "z\n")
        self.commit("TECHNICAL #5 something already on origin")
        self.git("push", "-q", "origin", "main")
        self.git("reset", "-q", "--hard", "HEAD~1")
        refused = self.sync(release, check=False)
        self.assertEqual(refused.returncode, 1)
        self.assertIn("does not contain origin/main", refused.stderr)

    # --- the probes of the review: the publish must not stay blocked after the first release ---------------------------

    def test_probe_a_private_edit_of_the_props_after_a_synced_release_does_not_block(self):
        self.released_and_published()
        before = self.public_tip()
        self.write(PROPS, "<Project><PropertyGroup>\n<Version>1.0.1</Version>\n<Other/>\n</PropertyGroup></Project>\n")
        self.commit("TECHNICAL #8 edit the props in private")
        self.publish()                                               # the bare remote refuses anything but a fast-forward
        tip = self.assert_fast_forward(before)
        self.assertEqual(self.git("rev-list", "--parents", "-n", "1", tip, cwd=self.pub).stdout.split()[1], before)
        self.assertIn("<Other/>", self.git("show", f"{tip}:{PROPS}", cwd=self.pub).stdout)

    def test_probe_b_bumping_version_and_manifest_in_private_after_a_release_does_not_block(self):
        self.released_and_published()
        before = self.public_tip()
        self.write(PROPS, "<Project><PropertyGroup>\n<Version>1.0.2</Version>\n</PropertyGroup></Project>\n")
        self.write(".release-please-manifest.json", '{".": "1.0.2"}\n')
        self.commit("TECHNICAL #8 bump the version after a failed release")
        self.publish()
        tip = self.assert_fast_forward(before)
        self.assertEqual(self.git("show", f"{tip}:.release-please-manifest.json", cwd=self.pub).stdout, '{".": "1.0.2"}\n')

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

    def test_a_release_pr_merged_with_a_merge_commit_is_accepted_once_its_commit_is_synced(self):
        self.publish()
        self.write("b.txt", "b\n")
        self.commit("FEATURE #2 add thing")
        self.publish()
        work = self.public_clone()
        self.git("checkout", "-q", "-b", "release-please--branches--main", cwd=work)
        props = (work / PROPS).read_text().replace("<Version>1.0.0</Version>", "<Version>1.0.1</Version>")
        (work / PROPS).write_text(props)
        self.write("CHANGELOG.md", "# Changelog\n\n## 1.0.1\n", root=work)
        self.write(".release-please-manifest.json", '{".": "1.0.1"}\n', root=work)
        commit = self.commit("chore: release dotnet 1.0.1", root=work)
        self.git("checkout", "-q", "main", cwd=work)
        run(work, "git", "merge", "--no-ff", "-q", "-m", "Merge pull request #1 from x/release", "release-please--branches--main", env=self.env)
        self.git("push", "-q", "origin", "HEAD:refs/heads/main", cwd=work)
        blocked = self.publish(check=False)
        self.assertEqual(blocked.returncode, 1)
        self.assertIn(commit, blocked.stderr)                        # the merge itself is accepted; its commit has to be synced
        self.sync(commit)
        self.publish()
        self.assertIn("<Version>1.0.1</Version>", self.git("show", f"main:{PROPS}", cwd=self.pub).stdout)

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
