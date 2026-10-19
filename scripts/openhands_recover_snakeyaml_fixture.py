#!/usr/bin/env python3
"""Recover the recorded disposable SnakeYAML Git fixture, only on exact SHA match.

No LLM, scanner, network, Maven or existing task database is touched. Rebuild
Git object bytes from the versioned one-file fixture and bounded historical
commit metadata; materialize only after exact SHA identity is proven.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "tests/fixtures/maven-single-module-direct/pom.xml"
TARGET = Path("/tmp/openhands-real-remediation-snakeyaml-v1")
EXPECTED = "f44f94c2b2ec553fc3276e36e6a99a0dcc4cd13a"
IDENTITY = "Remediation Test <test@example.invalid>"
MESSAGE = "Vulnerable baseline\n"


def object_sha(kind: str, content: bytes) -> str:
    prefix = f"{kind} {len(content)}\0".encode()
    return hashlib.sha1(prefix + content).hexdigest()


def git(*args: str, cwd: Path, data: bytes | None = None) -> str:
    result = subprocess.run(["git", *args], cwd=cwd, input=data,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            timeout=30, check=True)
    return result.stdout.decode().strip()


def recover(*, materialize: bool) -> None:
    if TARGET.is_symlink():
        raise ValueError("Refusing symlinked fixture directory")
    if not SOURCE.is_file() or SOURCE.is_symlink():
        raise ValueError("Versioned source POM absent or symlinked")
    pom = SOURCE.read_bytes()
    if b"snakeyaml" not in pom or b"1.33" not in pom:
        raise ValueError("Versioned source no longer resembles the original fixture")
    blob = object_sha("blob", pom)
    tree_bytes = b"100644 pom.xml\0" + bytes.fromhex(blob)
    tree = object_sha("tree", tree_bytes)

    # Conversation records show the root commit was made on 2026-10-18,
    # immediately before the 21:06 UTC confirmation. Search a conservative
    # bounded window, including possible local timezone renderings.
    begin = int(datetime(2026, 10, 18, 12, tzinfo=timezone.utc).timestamp())
    end = int(datetime(2026, 10, 19, 6, tzinfo=timezone.utc).timestamp())
    zones = ("+0000", "-0400", "-0500")
    match: bytes | None = None
    for zone in zones:
        for author_sec in range(begin, end):
            author = f"author {IDENTITY} {author_sec} {zone}\n"
            for delta in range(0, 6):
                committer = f"committer {IDENTITY} {author_sec + delta} {zone}\n"
                body = (f"tree {tree}\n" + author + committer +
                        "\n" + MESSAGE).encode()
                if object_sha("commit", body) == EXPECTED:
                    match = body
                    break
            if match:
                break
        if match:
            break

    print("Source:", SOURCE)
    print("POM blob:", blob)
    print("Git tree:", tree)
    if match is None:
        print("BLOCKED: Exact original commit not reproduced. No directory created.")
        raise SystemExit(2)
    print("Exact original commit identity: VERIFIED", EXPECTED)
    if not materialize:
        print("Dry run only; use --materialize to create the verified disposable fixture")
        return

    if TARGET.exists():
        # Resume only an identical partial recovery; never overwrite work.
        if not TARGET.is_dir() or not (TARGET / ".git").is_dir():
            raise ValueError("Existing target is not an ordinary Git repository")
        if git("rev-parse", "HEAD", cwd=TARGET) != EXPECTED:
            raise ValueError("Existing HEAD differs from approved commit")
        if git("ls-tree", "-r", "--name-only", "HEAD", cwd=TARGET) != "pom.xml":
            raise ValueError("Existing commit contains unexpected files")
        existing_pom = TARGET / "pom.xml"
        if not existing_pom.is_file() or existing_pom.is_symlink():
            raise ValueError("Existing POM missing or symlinked")
        if existing_pom.read_bytes() != pom:
            raise ValueError("Existing POM differs; refusing changes")
        if git("status", "--porcelain", cwd=TARGET) not in ("?? pom.xml", ""):
            raise ValueError("Existing fixture has unexpected changes")
        print("Verified exact partial recovery; repairing Git index only")
        git("reset", "--mixed", "HEAD", cwd=TARGET)
        if git("status", "--porcelain", cwd=TARGET):
            raise ValueError("Fixture still not clean")
        print("RECOVERED: original fixture at", TARGET)
        print("HEAD:", EXPECTED)
        return

    TARGET.mkdir(mode=0o700)
    git("init", "-q", "-b", "main", cwd=TARGET)
    (TARGET / "pom.xml").write_bytes(pom)
    if git("hash-object", "-w", "pom.xml", cwd=TARGET) != blob:
        raise ValueError("Blob hash mismatch")
    if git("hash-object", "-w", "-t", "tree", "--stdin", cwd=TARGET,
           data=tree_bytes) != tree:
        raise ValueError("Tree hash mismatch")
    if git("hash-object", "-w", "-t", "commit", "--stdin", cwd=TARGET,
           data=match) != EXPECTED:
        raise ValueError("Commit hash mismatch")
    git("update-ref", "refs/heads/main", EXPECTED, cwd=TARGET)
    # update-ref does not populate the index; reset --mixed does, without
    # modifying the working-tree POM.
    git("reset", "--mixed", "HEAD", cwd=TARGET)
    if git("rev-parse", "HEAD", cwd=TARGET) != EXPECTED:
        raise ValueError("Materialized HEAD differs from expected commit")
    if git("status", "--porcelain", cwd=TARGET):
        raise ValueError("Materialized fixture is not clean")
    print("RECOVERED: original fixture at", TARGET)
    print("HEAD:", EXPECTED)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--materialize", action="store_true")
    args = parser.parse_args()
    recover(materialize=args.materialize)
