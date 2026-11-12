#!/usr/bin/env python3
"""Logic of the private-to-public mirror (story #1659, trimmed by #3781): commit-subject mapping, the sync-back check, the merge message.

Used by the publish script (the filter's --commit-callback, the sync-back check, the merge commit message) and by
scripts/apply-public-change.sh, both absent from the public mirror; pinned by scripts/test_publish_mirror.py. Stdlib only, no network.

The mapping is part of the public history's identity: once a mapped commit is published, its hash depends on this
function, so a change to `map_message` rewrites every public commit after the published boundary and the non-force
push starts failing. Change it only with a new boundary.
"""
import functools
import os
import re
import subprocess
import sys

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


def _git(repo, *args, check=True):
    result = subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True)
    if check and result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result


def _is_ancestor(repo, ancestor, descendant):
    return _git(repo, "merge-base", "--is-ancestor", ancestor, descendant, check=False).returncode == 0


EXIT_OK, EXIT_REFUSED = 0, 1
TRAILER = "Public-Sync"
_FULL_SHA = re.compile(r"^[0-9a-f]{40}$")
MERGE_SUBJECT = "chore: merge the private history into the public mirror"


def recorded_syncs(repo, head):
    """Full shas of the public commits that private history records as absorbed: the `Public-Sync: <sha>` trailers in
    the history of `head`. The sync script writes one; a public change copied into private by hand carries one too."""
    out = _git(repo, "log", f"--format=%(trailers:key={TRAILER},valueonly)", head).stdout
    return {line.strip() for line in out.splitlines() if _FULL_SHA.match(line.strip())}


def _paths(repo, *args):
    return [p for p in _git(repo, "diff-tree", "-r", "--name-only", "--root", "--no-commit-id", *args).stdout.split("\n") if p]


def check_extra(repo, public, head):
    """Sync-back gate of the publish, run on the filtered clone. The commits on the public side that the filtered head
    does not contain are examined oldest first:
      - our own publish merge (tree equal to its second parent's, which the head contains) and a merge that changes nothing
        against its first parent are accepted (the commits they bring are examined themselves);
      - a commit whose full sha private history records in a `Public-Sync:` trailer is accepted, whatever it touched;
      - any other commit is refused, naming the commit and a path it touches: a contributor's change comes back through
        scripts/apply-public-change.sh, which writes the trailer.
    Returns (exit code, message, offending sha)."""
    extra = _git(repo, "rev-list", "--topo-order", "--reverse", f"{head}..{public}").stdout.split()
    recorded = recorded_syncs(repo, head)
    for sha in extra:
        if sha in recorded:
            continue
        parents = _git(repo, "rev-list", "--parents", "-n", "1", sha).stdout.split()[1:]
        if len(parents) > 1:
            own = (_git(repo, "rev-parse", f"{sha}^{{tree}}").stdout == _git(repo, "rev-parse", f"{parents[-1]}^{{tree}}").stdout
                   and _is_ancestor(repo, parents[-1], head))
            touched = _paths(repo, parents[0], sha)
            if not own and touched:
                return EXIT_REFUSED, f"public commit {sha} is a merge this publish did not make and it touches {touched[0]}", sha
            continue
        touched = _paths(repo, sha)
        return EXIT_REFUSED, (f"public commit {sha} touches {touched[0] if touched else 'nothing'} and is not recorded in private main "
                              f"(no '{TRAILER}: {sha}' trailer in its history; a contributor's change: scripts/apply-public-change.sh {sha} --work-item <id>; "
                              f"anything else: copy the change into private main with a '{TRAILER}: {sha}' trailer in its commit message)"), sha
    return EXIT_OK, "", None


def merge_message():
    """Message of the mirror's merge commit (parents: public tip, filtered head): a `chore:` subject, so it is no release entry."""
    return MERGE_SUBJECT + "\n"


def main(argv):
    command = argv[1] if len(argv) > 1 else ""
    try:
        if command == "check-extra" and len(argv) == 5:
            code, message, _sha = check_extra(argv[2], argv[3], argv[4])
            if message:
                print(("\u26d4 " if code == EXIT_REFUSED else "") + message, file=sys.stderr)
            return code
        if command == "merge-message" and len(argv) == 2:
            sys.stdout.write(merge_message())
            return 0
        if command == "is-recorded" and len(argv) == 5:
            return 0 if argv[4] in recorded_syncs(argv[2], argv[3]) else 1
    except RuntimeError as error:
        print(f"\u26d4 {error}", file=sys.stderr)
        return EXIT_REFUSED
    print("usage: publish_mirror.py check-extra <repo> <public> <head> | merge-message | is-recorded <repo> <head> <sha>", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
