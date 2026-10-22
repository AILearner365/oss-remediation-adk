"""Small durable private artifacts and bounded command execution."""
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import time


class Blocked(RuntimeError):
    pass


def require_independent_authority():
    """Legacy checkpoint: host authority isolation is explicitly deferred.

    LocalWorkspace, terminal and Maven execute as the same host user. This
    checkpoint does NOT establish a sandbox or protect records/credentials from
    that user. The approved product contract permits that known limitation;
    it no longer refuses execution unconditionally. Keep existing call sites
    for future authority enforcement, without a bypass flag or alternate mode.

    Deterministic validation, identity/integrity, baseline, policy and delivery
    authorization checks remain mandatory and are enforced by their callers.
    """
    return None


def read(path):
    return json.loads(Path(path).read_text())


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def write(path, value, *, exclusive=False):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    data = (json.dumps(value, sort_keys=True, indent=2) + "\n").encode()
    temp = path if exclusive else path.with_name(path.name + ".tmp")
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | (os.O_EXCL if exclusive else os.O_TRUNC), 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    if not exclusive:
        os.replace(temp, path)
    fd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


@contextmanager
def lock(state):
    with (Path(state) / "task.lock").open("a") as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        yield


def environment():
    # Omit explicit control-plane/model credential variables, not a host sandbox.
    allowed = {"PATH", "HOME", "USER", "LANG", "LC_ALL", "JAVA_HOME", "SSL_CERT_FILE",
               "SSL_CERT_DIR", "REQUESTS_CA_BUNDLE", "CURL_CA_BUNDLE", "TMPDIR",
               "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY",
               "http_proxy", "https_proxy", "all_proxy", "no_proxy"}
    return {k: v for k, v in os.environ.items() if k in allowed}


def command(argv, cwd, timeout, output=None, env=None):
    """No shell, no automatic retries; kill the process group on timeout."""
    started = time.monotonic()
    with subprocess.Popen([str(x) for x in argv], cwd=cwd, env=env or environment(),
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          start_new_session=True) as proc:
        timed_out = False
        try:
            stdout, stderr = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            os.killpg(proc.pid, signal.SIGKILL)
            stdout, stderr = proc.communicate()
        result = dict(exitCode=proc.returncode, timedOut=timed_out,
                      seconds=round(time.monotonic() - started, 3),
                      stdout=stdout.decode(errors="replace"), stderr=stderr.decode(errors="replace"))
    if output:
        # Private evidence, never copied into agent prompts or repository commits.
        write(output, result)
    return result
