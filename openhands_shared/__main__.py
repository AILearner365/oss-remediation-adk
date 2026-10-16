"""Run the Change 1 task registration/read API without an execution worker."""

from __future__ import annotations

import argparse
from pathlib import Path
from wsgiref.simple_server import make_server

from .api import TaskApi
from .store import SQLiteTaskStore


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", required=True, type=Path, help="durable SQLite database path")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8080, type=int)
    args = parser.parse_args()

    with SQLiteTaskStore(args.database) as store:
        server = make_server(args.host, args.port, TaskApi(store))
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            return 0
        finally:
            server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
