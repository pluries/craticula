#!/usr/bin/env python3
"""Logic of the private-to-public mirror (story #1659): commit-subject mapping, sync-back checks, Release Please's rule.

Used by the publish script (the filter's --commit-callback, the sync-back check, the merge commit message) and by the
sync script, both absent from the public mirror; pinned by scripts/test_publish_mirror.py. Stdlib only, no network.

The mapping is part of the public history's identity: once a mapped commit is published, its hash depends on this
function, so a change to `map_message` rewrites every public commit after the published boundary and the non-force
push starts failing. Change it only with a new boundary.
"""
import functools
import os
import re
import subprocess
import sys

# The only paths a public (Release Please) commit may touch; they are brought back to private main by
# scripts/sync-release-commit.sh. Release Please is gone (#3777); this guard goes with the mirror cleanup.
# README.md is allowed for one line only: the marked `Latest release:` line (see readme_problem below).
ALLOWED_PATHS = ("csharp/src/Directory.Build.props", "CHANGELOG.md", ".release-please-manifest.json", "README.md")
PROPS_PATH = ALLOWED_PATHS[0]
PLAIN_PATHS = ALLOWED_PATHS[1:3]     # copied whole
README_PATH = ALLOWED_PATHS[3]       # edited on the marked line only

_TYPES = {b"FEATURE": b"feat", b"FIX": b"fix", b"TECHNICAL": b"chore"}
_SUBJECT = re.compile(rb"^(FEATURE|FIX|TECHNICAL) #(\d+) (\S.*)$")
_MERGE = re.compile(rb"^Merge #(\d+): (\S.*)$")


def map_message(message: bytes) -> bytes:
    """`FEATURE|FIX|TECHNICAL #<id> text` -> `feat|fix|chore: text (#<id>)`; `Merge #<id>: text` -> `chore: merge text (#<id>)`.

    Only the first line changes: the body and the footers (BREAKING CHANGE: ...) pass through. A subject that matches
    neither shape is returned unchanged.
    """
    subject, sep, rest = message.partition(b"\n")
    text = subject.rstrip()
    m = _SUBJECT.match(text)
    if m:
        return b"%s: %s (#%s)" % (_TYPES[m.group(1)], m.group(3), m.group(2)) + sep + rest
    m = _MERGE.match(text)
    if m:
        return b"chore: merge %s (#%s)" % (m.group(2), m.group(1)) + sep + rest
    return message


@functools.lru_cache(maxsize=None)
def _frozen(path: str) -> frozenset:
    with open(path, "rb") as handle:
        return frozenset(line.strip() for line in handle if line.strip())


def map_unless_frozen(original_id: bytes, message: bytes, frozen_file: str) -> bytes:
    """The filter's callback body: commits at or before the published boundary keep their message byte for byte."""
    return message if original_id in _frozen(frozen_file) else map_message(message)


def drop_private_changes(commit, frozen_file: str, parents, exceptions) -> None:
    """The filter's callback body for a private folder that has one public exception (#1665, ADR 0004): every change under a
    private `parent` (or at the path `parent` itself, as the plain path filter did) is dropped, except under an `exception` folder, and
    only in a commit AFTER the frozen set. A commit at or before it drops the exception too, so no hash already public changes.
    Under an exception only regular files (and deletions) are published: a symlink or a submodule pointer would put a private
    path or a private commit id into the mirror."""
    keep = commit.original_id not in _frozen(frozen_file)
    private = tuple(parent.encode() + b"/" for parent in parents)
    exact = tuple(parent.encode() for parent in parents)
    public = tuple(exception.encode() + b"/" for exception in exceptions) if keep else ()

    def published(change) -> bool:
        if change.filename in exact:
            return False
        if not change.filename.startswith(private):
            return True
        return change.filename.startswith(public) and (change.type == b"D" or change.mode in (b"100644", b"100755"))

    commit.file_changes = [c for c in commit.file_changes if published(c)]


_CONVENTIONAL = re.compile(r"^(?P<type>[A-Za-z]+)(\([^)]*\))?(?P<bang>!)?: \S")
_BREAKING = re.compile(r"^BREAKING[ -]CHANGE: ", re.MULTILINE)
# Release Please (googleapis/release-please src/commit.ts splitMessages, read at v17.3.0, the version the pinned action
# bundles) splits one commit message into several entries at every blank line that is followed by `type: `; each entry is
# parsed as a conventional commit of its own. Mirrored here so the merge commit's body can be tested.
_SPLIT = re.compile(r"\r?\n\r?\n(?=(?:feat|fix|docs|style|refactor|perf|test|build|ci|chore|revert)(?:\(.*?\))?: )")
_RANK = {None: 0, "patch": 1, "minor": 2, "major": 3}


def _entry_type(entry: str):
    m = _CONVENTIONAL.match(entry.split("\n", 1)[0])
    if m is None:
        return None
    if _BREAKING.search(entry) or m.group("bang") is not None:
        return "major"
    return {"feat": "minor", "fix": "patch"}.get(m.group("type").lower())


def release_type(message: str):
    """Release Please's rule for one commit message: every entry (see _SPLIT) counts; feat -> minor, fix -> patch,
    `!` or a BREAKING CHANGE footer -> major; the strongest wins. Anything else (chore, docs, merge, non-conventional)
    -> None, which opens no release."""
    best = None
    for entry in _SPLIT.split(message):
        found = _entry_type(entry)
        if _RANK[found] > _RANK[best]:
            best = found
    return best


def _git(repo, *args, check=True):
    result = subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True)
    if check and result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result


def _entry(repo, rev, path):
    """(mode, blob id) of `path` at `rev`, or None when absent."""
    out = _git(repo, "ls-tree", rev, "--", path, check=False).stdout.strip()
    if not out:
        return None
    meta, _, _name = out.partition("\t")
    mode, _kind, blob = meta.split()
    return mode, blob


def _blob(repo, rev, path):
    found = _entry(repo, rev, path)
    return found[1] if found else None


def _is_ancestor(repo, ancestor, descendant):
    return _git(repo, "merge-base", "--is-ancestor", ancestor, descendant, check=False).returncode == 0


EXIT_OK, EXIT_REFUSED, EXIT_SYNC_NEEDED = 0, 1, 3
TRAILER = "Public-Sync"
_FULL_SHA = re.compile(r"^[0-9a-f]{40}$")
MERGE_SUBJECT = "chore: merge the private history into the public mirror"
MERGE_LIST_CAP = 200


def recorded_syncs(repo, head):
    """Full shas of the public commits that private history records as absorbed: the `Public-Sync: <sha>` trailers in
    the history of `head`. The sync script writes one; a public change copied into private by hand carries one too."""
    out = _git(repo, "log", f"--format=%(trailers:key={TRAILER},valueonly)", head).stdout
    return {line.strip() for line in out.splitlines() if _FULL_SHA.match(line.strip())}


def _paths(repo, *args):
    return [p for p in _git(repo, "diff-tree", "-r", "--name-only", "--root", "--no-commit-id", *args).stdout.split("\n") if p]


README_MARKER = "x-release-please-version"
README_LINE_PREFIX = "Latest release: "
_SEMVER = re.compile(r"(?<![\w.])\d+\.\d+\.\d+(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?(?![\w.+-])")


def _marked_line(line):
    """The semver match of a `Latest release: <semver> <!-- x-release-please-version -->` line, else None (also None
    when the line holds no semver or more than one)."""
    if README_MARKER not in line or not line.startswith(README_LINE_PREFIX):
        return None
    found = list(_SEMVER.finditer(line))
    return found[0] if len(found) == 1 else None


def _marked_lines(text):
    return [n for n, line in enumerate(text.split("\n")) if README_MARKER in line]


def readme_problem(old_text, new_text):
    """None when the README change from `old_text` to `new_text` is exactly one changed line, the marked `Latest release:`
    line holding one semver before and after and nothing else different; else the reason it is refused."""
    old_lines, new_lines = old_text.split("\n"), new_text.split("\n")
    if len(old_lines) != len(new_lines):
        return "it changes the number of lines; only the marked 'Latest release:' line may change"
    changed = [n for n, (a, b) in enumerate(zip(old_lines, new_lines)) if a != b]
    if len(changed) != 1:
        return f"it changes {len(changed)} lines; only the one marked 'Latest release:' line may change"
    old_line, new_line = old_lines[changed[0]], new_lines[changed[0]]
    if len(_marked_lines(old_text)) != 1 or _marked_line(old_line) is None:
        return f"line {changed[0] + 1} is not the single marked 'Latest release:' line holding one semantic version"
    if _marked_line(new_line) is None:
        return f"line {changed[0] + 1} must keep the 'Latest release:' marker line with exactly one semantic version, has {new_line.strip()!r}"
    old_match, new_match = _marked_line(old_line), _marked_line(new_line)
    if old_line[:old_match.start()] + old_line[old_match.end():] != new_line[:new_match.start()] + new_line[new_match.end():]:
        return f"line {changed[0] + 1} changes more than the version ({old_line.strip()!r} to {new_line.strip()!r})"
    return None


def _readme_texts(repo, base, sha):
    old, new = _blob(repo, base, README_PATH) if base else None, _blob(repo, sha, README_PATH)
    if old is None or new is None:
        return None, None, f"{README_PATH} is added or deleted; only its marked 'Latest release:' line may change"
    for rev in (base, sha):
        mode = _entry(repo, rev, README_PATH)[0]
        if mode not in ("100644", "100755"):
            return None, None, f"{README_PATH} at {rev} is not a regular file (mode {mode})"
    old_data, new_data = _cat(repo, old), _cat(repo, new)
    if b"\x00" in old_data or b"\x00" in new_data:
        return None, None, f"{README_PATH} contains a NUL byte"
    try:
        return old_data.decode("utf-8"), new_data.decode("utf-8"), None
    except UnicodeDecodeError:
        return None, None, f"{README_PATH} is not UTF-8"


def readme_commit_problem(repo, sha):
    """Why the public commit `sha` may not change README.md, or None when its change is the marked line only."""
    parents = _git(repo, "rev-list", "--parents", "-n", "1", sha).stdout.split()[1:]
    old, new, problem = _readme_texts(repo, parents[0] if parents else None, sha)
    return problem or readme_problem(old, new)


def check_extra(repo, public, head):
    """Sync-back gate of the publish, run on the filtered clone. The commits on the public side that the filtered head
    does not contain are examined oldest first:
      - our own publish merge (tree equal to its second parent's, which the head contains) and a merge whose diff
        against its first parent touches only ALLOWED_PATHS are accepted (the commits they bring are examined themselves);
      - a commit whose full sha private history records in a `Public-Sync:` trailer is accepted, whatever it touched;
      - any other commit touching a path outside ALLOWED_PATHS is refused, naming commit and path;
      - any other commit touching only ALLOWED_PATHS has to be synced first (EXIT_SYNC_NEEDED, the oldest one is named).
    Nothing compares file contents with the head's: after the first release the head legitimately moves on.
    Returns (exit code, message, sha to sync from)."""
    extra = _git(repo, "rev-list", "--topo-order", "--reverse", f"{head}..{public}").stdout.split()
    recorded = recorded_syncs(repo, head)
    pending = None
    for sha in extra:
        parents = _git(repo, "rev-list", "--parents", "-n", "1", sha).stdout.split()[1:]
        if sha in recorded:
            continue
        if len(parents) > 1:
            own = (_git(repo, "rev-parse", f"{sha}^{{tree}}").stdout == _git(repo, "rev-parse", f"{parents[-1]}^{{tree}}").stdout
                   and _is_ancestor(repo, parents[-1], head))
            outside = [p for p in _paths(repo, parents[0], sha) if p not in ALLOWED_PATHS]
            if not own and outside:
                return EXIT_REFUSED, f"public commit {sha} is a merge this publish did not make and it touches {outside[0]} (only {', '.join(ALLOWED_PATHS)} may change on the public side)", None
            continue
        for path in _paths(repo, sha):
            problem = None
            if path not in ALLOWED_PATHS:
                problem = f"touches {path}; only {', '.join(ALLOWED_PATHS)} may change on the public side"
            elif path == README_PATH:
                why = readme_commit_problem(repo, sha)
                if why:
                    problem = f"touches {path} beyond the marked 'Latest release:' line ({why})"
            if problem:
                return EXIT_REFUSED, (f"public commit {sha} {problem} "
                                      f"(a contributor's change: scripts/apply-public-change.sh {sha} --work-item <id>; anything else: copy the change into private main "
                                      f"with a '{TRAILER}: {sha}' trailer in its commit message)"), None
        if pending is None:
            pending = sha
    if pending:
        return EXIT_SYNC_NEEDED, (
            f"public commit {pending} is not recorded in private main (no '{TRAILER}: {pending}' trailer in its history): "
            f"from a work branch run scripts/sync-release-commit.sh {pending} --work-item <id>, merge that to main, then publish again"), pending
    return EXIT_OK, "", None


_VERSION_ELEMENT = re.compile(r"<Version>([^<]*)</Version>")
_VERSION_VALUE = re.compile(r"^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$")


def _versions(text, where):
    found = _VERSION_ELEMENT.findall(text)
    if len(found) != 1:
        raise RuntimeError(f"{where} must hold exactly one <Version>, found {len(found)}")
    value = found[0].strip()
    if not _VERSION_VALUE.match(value):
        raise RuntimeError(f"{where} holds the <Version> value {value!r}, which is not a plain semantic version")
    return value


def read_version(repo):
    with open(os.path.join(repo, PROPS_PATH), encoding="utf-8") as handle:
        return _versions(handle.read(), PROPS_PATH)


def _cat(repo, blob):
    return subprocess.run(["git", "-C", repo, "cat-file", "blob", blob], capture_output=True, check=True).stdout


def _first_difference(old, new):
    old_lines, new_lines = old.splitlines(), new.splitlines()
    for number in range(max(len(old_lines), len(new_lines))):
        a = old_lines[number] if number < len(old_lines) else "<end of file>"
        b = new_lines[number] if number < len(new_lines) else "<end of file>"
        if a != b:
            return f"line {number + 1}: parent has {a.strip()!r}, public commit has {b.strip()!r}"
    return "line endings differ"


def _read_private(repo, path):
    full = os.path.join(repo, path)
    if os.path.islink(full):
        raise RuntimeError(f"{path} is a symbolic link in the private working tree; refusing to write through it")
    if not os.path.exists(full):
        return None
    with open(full, "rb") as handle:
        return handle.read()


def _write(repo, path, data):
    full = os.path.join(repo, path)
    os.makedirs(os.path.dirname(full) or ".", exist_ok=True)
    with open(full, "wb") as handle:
        handle.write(data)


def apply_release(repo, sha):
    """Bring the public release commit `sha` into the working tree of `repo`; return the paths changed.

    Only the <Version> value is taken from the public props file (the private file is edited in place, never replaced):
    the public commit's change to that file must be that value and nothing else, or the sync refuses and names the
    difference. CHANGELOG.md and the manifest are copied whole; both must be regular files without a NUL byte. Refuses a
    merge commit, a commit touching another path, and a private file that moved on since the commit's parent (a silent
    overwrite of a private edit is worse than a manual merge)."""
    parents = _git(repo, "rev-list", "--parents", "-n", "1", sha).stdout.split()[1:]
    if len(parents) != 1:
        raise RuntimeError(f"{sha} must be a release commit with one parent, it has {len(parents)} (sync the single-parent release commit instead)")
    base = parents[0]
    for path in _paths(repo, sha):
        if path not in ALLOWED_PATHS:
            raise RuntimeError(f"{sha} touches {path}; only {', '.join(ALLOWED_PATHS)} may change on the public side")
    writes = []

    # The version value, in the private props file.
    pub_blob, old_blob = _blob(repo, sha, PROPS_PATH), _blob(repo, base, PROPS_PATH)
    if pub_blob != old_blob:
        if pub_blob is None or old_blob is None:
            raise RuntimeError(f"{PROPS_PATH} is added or deleted by {sha}; only its <Version> value may change")
        pub_text, old_text = _cat(repo, pub_blob).decode("utf-8"), _cat(repo, old_blob).decode("utf-8")
        new_version, old_version = _versions(pub_text, f"{PROPS_PATH} at {sha}"), _versions(old_text, f"{PROPS_PATH} at {base}")
        masked_pub, masked_old = _VERSION_ELEMENT.sub("<Version>@</Version>", pub_text), _VERSION_ELEMENT.sub("<Version>@</Version>", old_text)
        if masked_pub != masked_old:
            raise RuntimeError(f"{sha} changes {PROPS_PATH} beyond the <Version> value ({_first_difference(masked_old, masked_pub)}); merge it by hand")
        current = _read_private(repo, PROPS_PATH)
        if current is None:
            raise RuntimeError(f"{PROPS_PATH} is missing in the private working tree")
        private_text = current.decode("utf-8")
        private_version = _versions(private_text, PROPS_PATH)
        if private_version != new_version:
            if private_version != old_version:
                raise RuntimeError(f"<Version> in {PROPS_PATH} was edited in private main ({private_version}) since the public commit's parent ({old_version}); merge it by hand")
            writes.append((PROPS_PATH, _VERSION_ELEMENT.sub(lambda _m: f"<Version>{new_version}</Version>", private_text, count=1).encode("utf-8")))

    # The two plain-text files, copied whole.
    for path in PLAIN_PATHS:
        entry = _entry(repo, sha, path)
        if entry is None:
            if _entry(repo, base, path) is None:
                continue
            raise RuntimeError(f"{sha} deletes {path}; refusing")
        mode, target = entry
        if mode not in ("100644", "100755"):
            raise RuntimeError(f"{path} at {sha} is not a regular file (mode {mode}); refusing")
        data = _cat(repo, target)
        if b"\x00" in data:
            raise RuntimeError(f"{path} at {sha} contains a NUL byte; refusing")
        current = _read_private(repo, path)
        if current == data:
            continue
        have = None if current is None else subprocess.run(
            ["git", "-C", repo, "hash-object", "--stdin"], input=current, capture_output=True, check=True).stdout.decode().strip()
        if have != _blob(repo, base, path):
            raise RuntimeError(f"{path} was edited in private main since the public commit's parent; merge it by hand")
        writes.append((path, data))

    # The README: the marked line only, edited in the private copy in place (never the public file copied).
    if _blob(repo, sha, README_PATH) != _blob(repo, base, README_PATH):
        old_text, new_text, problem = _readme_texts(repo, base, sha)
        problem = problem or readme_problem(old_text, new_text)
        if problem:
            raise RuntimeError(f"{sha} changes {README_PATH} beyond the marked 'Latest release:' line: {problem}; merge it by hand")
        pub_line = next(line for line in new_text.split("\n") if README_MARKER in line)
        old_line = next(line for line in old_text.split("\n") if README_MARKER in line)
        new_version, old_version = _marked_line(pub_line).group(0), _marked_line(old_line).group(0)
        current = _read_private(repo, README_PATH)
        if current is None:
            raise RuntimeError(f"{README_PATH} is missing in the private working tree")
        private_text = current.decode("utf-8")
        marked = _marked_lines(private_text)
        private_lines = private_text.split("\n")
        if len(marked) != 1 or _marked_line(private_lines[marked[0]]) is None:
            raise RuntimeError(f"{README_PATH} in private main has no single marked 'Latest release:' line with one semantic version; merge it by hand")
        match = _marked_line(private_lines[marked[0]])
        if match.group(0) != new_version:
            if match.group(0) != old_version:
                raise RuntimeError(f"the 'Latest release:' line in {README_PATH} was edited in private main ({match.group(0)}) since the public commit's parent ({old_version}); merge it by hand")
            line = private_lines[marked[0]]
            private_lines[marked[0]] = line[:match.start()] + new_version + line[match.end():]
            writes.append((README_PATH, "\n".join(private_lines).encode("utf-8")))
    for path, data in writes:      # every check passed: nothing is written before this point
        _write(repo, path, data)
    return [path for path, _data in writes]


_TYPE_RANK = {"feat": 1, "fix": 2, "perf": 3}


def merge_message(repo, public, head, cap=MERGE_LIST_CAP):
    """Message of the mirror's merge commit (parents: public tip, filtered head).

    Release Please reads the merge commit, dated at publish time, and walks history by date until the last release, so
    the commits this merge brings in that are dated before the release commit are never counted by themselves.
    Release Please splits one message into entries at each blank line followed by `type: ` (see _SPLIT), so the body
    lists the mapped subject of every non-merge commit PUBLIC_TIP..HEAD as its own paragraph (a BREAKING CHANGE footer
    stays with its commit), strongest first, at most `cap`, then one count line. Commits dated after the newest public-only commit are left out:
    Release Please counts those by themselves, listing them would double them in the changelog.
    The subject stays a `chore:` so the merge itself counts for nothing."""
    cutoff = _git(repo, "log", "--no-merges", "-1", "--format=%ct", f"{head}..{public}").stdout.strip()
    raw = _git(repo, "log", "--no-merges", "--format=%x01%ct%x00%s%x00%b", f"{public}..{head}").stdout
    entries = []
    for chunk in raw.split("\x01")[1:]:
        stamp, subject, body = chunk.split("\x00", 2)
        if cutoff and int(stamp) > int(cutoff):
            continue
        m = _CONVENTIONAL.match(subject)
        if m is None or not _SPLIT.match("\n\n" + subject):
            if m is None or m.group("bang") is None:
                continue
        footers = [line for line in body.splitlines() if _BREAKING.match(line)]
        subject = subject.strip()
        if m.group("bang") is not None:
            # Release Please's split pattern has no `!`: `feat!: x` after a blank line would stay inside the previous entry.
            # State the break as a footer on a plain `feat: x` instead.
            subject = re.sub(r"^([A-Za-z]+(?:\([^)]*\))?)!: ", r"\1: ", subject)
            if not footers:
                footers = [f"BREAKING CHANGE: {subject.split(': ', 1)[1]}"]
        breaking = bool(footers)
        entries.append((0 if breaking else _TYPE_RANK.get(m.group("type").lower(), 4), "\n\n".join([subject, *footers])))
    entries.sort(key=lambda item: item[0])     # stable: strongest type first, newest first within a type
    paragraphs = [text for _rank, text in entries[:cap]]
    if len(entries) > cap:
        paragraphs.append(f"... and {len(entries) - cap} more commits not listed")
    return "\n\n".join([MERGE_SUBJECT, *paragraphs]) + "\n"


def main(argv):
    command = argv[1] if len(argv) > 1 else ""
    try:
        if command == "check-extra" and len(argv) == 5:
            code, message, _sha = check_extra(argv[2], argv[3], argv[4])
            if message:
                print(("\u26d4 " if code == EXIT_REFUSED else "") + message, file=sys.stderr)
            return code
        if command == "apply-release" and len(argv) == 4:
            for path in apply_release(argv[2], argv[3]):
                print(path)
            return 0
        if command == "version" and len(argv) == 3:
            print(read_version(argv[2]))
            return 0
        if command == "merge-message" and len(argv) == 5:
            sys.stdout.write(merge_message(argv[2], argv[3], argv[4]))
            return 0
        if command == "is-recorded" and len(argv) == 5:
            return 0 if argv[4] in recorded_syncs(argv[2], argv[3]) else 1
    except RuntimeError as error:
        print(f"\u26d4 {error}", file=sys.stderr)
        return EXIT_REFUSED
    print("usage: publish_mirror.py check-extra <repo> <public> <head> | apply-release <repo> <sha> | version <repo> | "
          "merge-message <repo> <public> <head> | is-recorded <repo> <head> <sha>", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
