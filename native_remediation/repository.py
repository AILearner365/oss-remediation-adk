"""Approved revision preparation and immutable, independently exported Git trees."""
import fnmatch
import os
from pathlib import Path
import subprocess
import tempfile

from .files import Blocked, environment


def git(repository, *args, input=None, env=None):
    result = subprocess.run(["git", "-c", "core.hooksPath=/dev/null", "-c", "core.fsmonitor=false",
        "-C", str(repository), *args], input=input, env=env or environment(),
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=120)
    if result.returncode:
        raise Blocked("Git operation failed: " + args[0])
    return result.stdout


def text(repository, *args, **kwargs):
    return git(repository, *args, **kwargs).decode().strip()


def url(task):
    return "https://github.com/" + task["repository"] + ".git"


def verify_base(task):
    refs = text(Path.cwd(), "ls-remote", url(task), "refs/heads/" + task["base_branch"]).split()
    if not refs or refs[0] != task["base_sha"]:
        raise Blocked("Remote base differs from the approved SHA")


def prepare(state, task):
    verify_base(task)
    mirror = state / "source.git"
    git(state, "clone", "--bare", "--single-branch", "--branch", task["base_branch"], url(task), str(mirror))
    if text(mirror, "rev-parse", task["base_branch"]) != task["base_sha"]:
        raise Blocked("Remote changed during clone")
    workspace = state / "workspace"
    git(mirror, "worktree", "add", "--detach", str(workspace), task["base_sha"])
    return workspace


def snapshot(workspace, task):
    if text(workspace, "remote", "get-url", "origin") != url(task):
        raise Blocked("Workspace remote identity changed")
    git(workspace, "merge-base", "--is-ancestor", task["base_sha"], "HEAD")
    with tempfile.TemporaryDirectory(prefix="native-index-") as directory:
        env = dict(environment(), GIT_INDEX_FILE=str(Path(directory) / "index"))
        git(workspace, "read-tree", "HEAD", env=env)
        git(workspace, "add", "-A", env=env)
        return text(workspace, "write-tree", env=env)


def changed_paths(workspace, task, tree):
    rows = git(workspace, "diff", "--no-renames", "--name-only", "-z", task["base_sha"], tree).split(b"\0")
    return [row.decode() for row in rows if row]


def check_paths(workspace, task, tree):
    changed = changed_paths(workspace, task, tree)
    p = task["policy"]
    for name in changed:
        if (not any(fnmatch.fnmatchcase(name, pattern) for pattern in p["allowed_paths"])
                or any(fnmatch.fnmatchcase(name, pattern) for pattern in p["protected_paths"])
                or any(part in {".git", ".github", ".mvn", "target"} for part in Path(name).parts)
                or Path(name).name in {".gitmodules", "osv-scanner.toml", ".osv-scanner.toml"}):
            raise Blocked("Change violates repository policy: " + name)
    return changed


def export(workspace, tree, destination):
    # Materialize exact blobs, not git archive: export-ignore/export-subst
    # attributes must not make the tested source differ from the delivered tree.
    rows = git(workspace, "ls-tree", "-r", "-z", tree).split(b"\0")
    entries = []
    for row in rows:
        if not row:
            continue
        metadata, name = row.split(b"\t", 1)
        mode, kind, sha = metadata.split()
        path = Path(os.fsdecode(name))
        if (mode not in (b"100644", b"100755") or kind != b"blob"
                or path.is_absolute() or ".." in path.parts or ".git" in path.parts):
            raise Blocked("Symlinks/submodules require a separately verified workspace adapter")
        entries.append((mode, sha, path))
    destination.mkdir(parents=True, exist_ok=False)
    blobs = git(workspace, "cat-file", "--batch", input=b"".join(sha + b"\n" for _, sha, _ in entries))
    offset = 0
    for mode, sha, path in entries:
        end = blobs.index(b"\n", offset)
        header = blobs[offset:end].split()
        if header[:2] != [sha, b"blob"]:
            raise Blocked("Git blob identity mismatch")
        size = int(header[2])
        start = end + 1
        target = destination / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(blobs[start:start + size])
        target.chmod(0o755 if mode == b"100755" else 0o644)
        offset = start + size + 1


def commit_tree(workspace, task, tree, conversation):
    env = dict(environment(), GIT_AUTHOR_NAME="OpenHands Remediation",
        GIT_AUTHOR_EMAIL="openhands-remediation@users.noreply.github.com",
        GIT_COMMITTER_NAME="OpenHands Remediation",
        GIT_COMMITTER_EMAIL="openhands-remediation@users.noreply.github.com")
    return text(workspace, "commit-tree", tree, "-p", task["base_sha"],
                input=("Verified OSS remediation (" + conversation + ")\n").encode(), env=env)
