"""Small process boundary, not an agent runtime: native terminal + build commands.

No host home, credentials, socket, SDK persistence or network is exposed.
Baseline evidence is read-only; acceptance decisions and claims are never mounted.
An operator-provisioned, immutable image must contain bash, Git, Java/Maven, OSV
2.6.0, and any offline artifacts/research/SBRI needed by the approved task.
"""
import os
from pathlib import Path
import subprocess
import stat
import sys
import uuid

from .contract import context
from .files import Blocked, command, environment


def check(task):
    image = task["sandbox"]["image"]
    if not image:
        raise Blocked("Provision and approve a pinned local sandbox image before preparation/run")
    result = subprocess.run(["docker", "image", "inspect", "--format", "{{.Id}}", image],
                            capture_output=True, text=True, timeout=20, env=environment())
    if result.returncode or result.stdout.strip() != image:
        raise Blocked("Approved sandbox image unavailable; no pull or host execution fallback")


def invocation(task, mounts, cwd, *, interactive=False, name=None, label=None, env=None):
    """Mount allowlist supplied only by trusted code; never by an agent action."""
    args = ["docker", "run", "--rm", "--pull=never", "--name", name or "oss-remediate-" + uuid.uuid4().hex,
            "--network=none", "--read-only", "--cap-drop=ALL", "--security-opt=no-new-privileges",
            "--pids-limit=256", "--memory=4g", "--cpus=2", "--user", f"{os.getuid()}:{os.getgid()}",
            "--tmpfs", "/tmp:rw,nosuid,nodev,size=1g,mode=1777", "--env", "HOME=/tmp",
            "--workdir", str(cwd), "--entrypoint", "/bin/bash"]
    if interactive:
        args.append("-i")
    if label:
        args += ["--label", "oss.conversation=" + label]
    for key, value in (env or {}).items():
        args += ["--env", key + "=" + value]
    for source, destination, writable in mounts:
        source = Path(source).resolve(strict=True)
        if any(c in str(source) + str(destination) for c in ",\n\r"):
            raise Blocked("Unsupported sandbox mount path")
        args += ["--mount", f"type=bind,src={source},dst={destination}" + ("" if writable else ",readonly")]
    return args + [task["sandbox"]["image"]]


def run(argv, cwd, timeout, output=None, *, task):
    """Only raw source/build outputs are writable. Decisions stay on the host."""
    cwd = Path(cwd).resolve(strict=True)
    cache = cwd.parent / "maven-cache"
    cache.mkdir(exist_ok=True)
    mounts = [(cwd, cwd, True), (cache, cache, True)]
    for arg in argv:
        if arg.startswith(("--sbom=", "--config=")):
            path = Path(arg.split("=", 1)[1]).resolve(strict=True)
            if not path.is_relative_to(cwd):
                mounts.append((path, path, False))
    args = invocation(task, mounts, cwd) + ["-c", 'exec "$@"', "sandbox", *map(str, argv)]
    name = args[args.index("--name") + 1]
    try:
        result = command(args, cwd, timeout, output)
    finally:
        # Killing a Docker client alone does not kill its container on timeout.
        stop_container(name)
    # Build outputs are untrusted too: do not follow host-visible symlinks or
    # block on FIFOs/devices when the host parses generated XML/JSON reports.
    for path in cwd.rglob("*"):
        mode = path.lstat().st_mode
        if not (stat.S_ISREG(mode) or stat.S_ISDIR(mode)):
            raise Blocked("Unsafe generated build output; symlinks/special files unsupported")
    return result


def shell(state):
    """Native TerminalTool shell_path entry point; one persistent container shell."""
    state, bound, task = context(state)
    check(task)
    control = state / "control"
    mounts = [(state / "workspace", control, True)]
    mounts.append((state / "workspace" / ".git", control / ".git", False))
    if (state / "source.git").is_dir():
        mounts.append((state / "source.git", state / "source.git", False))
    for source, destination in ((state / "baseline", Path("/baseline")),
                                (state / "baseline.json", Path("/baseline.json"))):
        mounts.append((source, destination, False))
    args = invocation(task, mounts, control, interactive=True,
        name="oss-agent-" + bound["conversationId"], label=bound["conversationId"],
        env={k: os.environ[k] for k in ("PS1", "PS2", "TERM") if k in os.environ})
    # Docker receives no host environment variables except its own CLI environment;
    # image entrypoint is overridden, and host credentials are never passed/mounted.
    os.execvpe(args[0], args + ["--noprofile", "--norc", *sys.argv[1:]], environment())


def stop_agent(state):
    """Quiesce all agent descendants before snapshot/acceptance, including daemons."""
    _, bound, _ = context(state)
    name = "oss-agent-" + bound["conversationId"]
    stop_container(name, conversation=bound["conversationId"])


def stop_container(name, *, conversation=None):
    result = subprocess.run(["docker", "ps", "-a", "--filter", "name=^/" + name + "$",
        "--format", "{{.Names}}"], capture_output=True, text=True, timeout=20, env=environment())
    if result.returncode:
        raise Blocked("Cannot confirm agent sandbox quiescence")
    if result.stdout.strip():
        if conversation:
            identity = subprocess.run(["docker", "inspect", "--format",
                '{{index .Config.Labels "oss.conversation"}}', name],
                capture_output=True, text=True, timeout=20, env=environment())
            if identity.returncode or identity.stdout.strip() != conversation:
                raise Blocked("Agent container identity mismatch")
        removed = subprocess.run(["docker", "rm", "-f", name],
            capture_output=True, timeout=20, env=environment())
        if removed.returncode:
            raise Blocked("Could not stop agent sandbox before validation")


def launcher(state):
    path = state / "sandbox-shell"
    contents = (f"#!{sys.executable}\nimport sys\nsys.path.insert(0, "
                f"{str(Path(__file__).resolve().parent.parent)!r})\n"
                f"from native_remediation.sandbox import shell\nshell({str(state)!r})\n")
    if path.exists():
        if path.read_text() != contents or path.is_symlink():
            raise Blocked("Sandbox launcher changed; inspect before resuming")
    else:
        path.write_text(contents)
        path.chmod(0o700)
    return path
