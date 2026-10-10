"""Dependency-free HTTP facade for one or more local Maven repositories."""

from __future__ import annotations

import threading
import urllib.parse
from contextlib import contextmanager
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Iterator


class _QuietMavenRepositoryHandler(SimpleHTTPRequestHandler):
    def __init__(
        self,
        *args: Any,
        repositories: tuple[Path, ...],
        requests: list[dict[str, Any]],
        **kwargs: Any,
    ):
        self.repositories = repositories
        self.requests = requests
        super().__init__(*args, directory=str(repositories[0]), **kwargs)

    def log_message(self, format: str, *args: Any) -> None:
        return None

    def translate_path(self, path: str) -> str:
        relative = Path(urllib.parse.unquote(urllib.parse.urlsplit(path).path).lstrip("/"))
        if ".." in relative.parts:
            return str(self.repositories[0] / "__invalid_path__")
        for repository in self.repositories:
            candidate = repository / relative
            if candidate.resolve().is_relative_to(repository.resolve()) and candidate.exists():
                self.requests.append(
                    {"path": f"/{relative.as_posix()}", "resolvedPath": str(candidate), "found": True}
                )
                return str(candidate)
        self.requests.append(
            {
                "path": f"/{relative.as_posix()}",
                "resolvedPath": str(self.repositories[0] / relative),
                "found": False,
            }
        )
        return str(self.repositories[0] / relative)


@contextmanager
def serve_maven_repository(
    repositories: tuple[Path, ...],
) -> Iterator[tuple[str, list[dict[str, Any]]]]:
    """Serve local Maven repositories on loopback for OSV Scanner native mode."""
    if not repositories:
        raise ValueError("At least one Maven repository is required")
    missing = [str(path) for path in repositories if not path.is_dir()]
    if missing:
        raise ValueError(f"Maven repository is unavailable: {', '.join(missing)}")

    requests: list[dict[str, Any]] = []
    handler = partial(_QuietMavenRepositoryHandler, repositories=repositories, requests=requests)
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, name="osv-maven-cache", daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/", requests
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
