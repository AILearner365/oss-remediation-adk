from __future__ import annotations

import ctypes
import errno
import os
import signal
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Mapping, Sequence


class ExperimentalIsolationUnavailable(RuntimeError):
    pass


@dataclass(frozen=True)
class IsolatedProcessResult:
    exit_code: int
    timed_out: bool
    error: str | None = None


class ExperimentalProcessIsolation:
    def __init__(self, run_root: Path):
        self.run_root = run_root
        self._prepared: dict[Path, Path] = {}

    @property
    def available(self) -> bool:
        return os.name == "nt" or _linux_isolation_backend() is not None

    @property
    def backend(self) -> str:
        if os.name == "nt":
            return "windows-low-integrity"
        return _linux_isolation_backend() or "unavailable"

    def prepare(self, repository: Path, cycle: int, historical_repositories: Sequence[Path]) -> Path:
        if not self.available:
            raise ExperimentalIsolationUnavailable(
                "Experimental shell isolation requires Windows mandatory integrity control, "
                "Linux Landlock, or usable Linux user and mount namespaces"
            )
        runtime = self.run_root / "temp" / "experimental-runtime" / f"cycle-{cycle}"
        runtime.mkdir(parents=True, exist_ok=True)
        if os.name == "nt":
            for historical in historical_repositories:
                _set_integrity_level(historical, "M")
            _set_integrity_level(repository, "L")
            _set_integrity_level(runtime, "L")
        self._prepared[repository.resolve()] = runtime.resolve()
        return runtime

    def run(
        self,
        command: Sequence[str],
        *,
        cwd: Path,
        environment: Mapping[str, str],
        stdout_path: Path,
        stderr_path: Path,
        timeout_seconds: int,
    ) -> IsolatedProcessResult:
        if not self.available:
            return IsolatedProcessResult(
                126,
                False,
                "Experimental shell isolation is unavailable on this runtime",
            )
        prepared = next(
            (
                (repository, runtime)
                for repository, runtime in self._prepared.items()
                if cwd.resolve() == repository or repository in cwd.resolve().parents
            ),
            None,
        )
        if prepared is None:
            return IsolatedProcessResult(126, False, "Experimental workspace was not prepared")
        repository, runtime = prepared
        if os.name == "nt":
            return _run_windows_low_integrity(
                command,
                cwd=cwd,
                environment=environment,
                stdout_path=stdout_path,
                stderr_path=stderr_path,
                timeout_seconds=timeout_seconds,
            )
        if _linux_isolation_backend() == "linux-landlock":
            return _run_linux_landlock(
                command,
                repository=repository,
                runtime=runtime,
                cwd=cwd,
                environment=environment,
                stdout_path=stdout_path,
                stderr_path=stderr_path,
                timeout_seconds=timeout_seconds,
            )
        return _run_linux_mount_namespace(
            command,
            repository=repository,
            runtime=runtime,
            cwd=cwd,
            environment=environment,
            stdout_path=stdout_path,
            stderr_path=stderr_path,
            timeout_seconds=timeout_seconds,
        )


def _set_integrity_level(path: Path, level: str) -> None:
    completed = subprocess.run(
        ["icacls", str(path), "/setintegritylevel", f"(OI)(CI){level}"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise ExperimentalIsolationUnavailable(
            f"Unable to apply {level} integrity boundary to {path}: {detail}"
        )


def _run_windows_low_integrity(
    command: Sequence[str],
    *,
    cwd: Path,
    environment: Mapping[str, str],
    stdout_path: Path,
    stderr_path: Path,
    timeout_seconds: int,
) -> IsolatedProcessResult:
    from ctypes import wintypes

    advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    handle_type = wintypes.HANDLE
    pointer_type = wintypes.LPVOID

    class SidAndAttributes(ctypes.Structure):
        _fields_ = [("Sid", pointer_type), ("Attributes", wintypes.DWORD)]

    class TokenMandatoryLabel(ctypes.Structure):
        _fields_ = [("Label", SidAndAttributes)]

    class StartupInfo(ctypes.Structure):
        _fields_ = [
            ("cb", wintypes.DWORD),
            ("lpReserved", wintypes.LPWSTR),
            ("lpDesktop", wintypes.LPWSTR),
            ("lpTitle", wintypes.LPWSTR),
            ("dwX", wintypes.DWORD),
            ("dwY", wintypes.DWORD),
            ("dwXSize", wintypes.DWORD),
            ("dwYSize", wintypes.DWORD),
            ("dwXCountChars", wintypes.DWORD),
            ("dwYCountChars", wintypes.DWORD),
            ("dwFillAttribute", wintypes.DWORD),
            ("dwFlags", wintypes.DWORD),
            ("wShowWindow", wintypes.WORD),
            ("cbReserved2", wintypes.WORD),
            ("lpReserved2", ctypes.POINTER(ctypes.c_byte)),
            ("hStdInput", handle_type),
            ("hStdOutput", handle_type),
            ("hStdError", handle_type),
        ]

    class ProcessInformation(ctypes.Structure):
        _fields_ = [
            ("hProcess", handle_type),
            ("hThread", handle_type),
            ("dwProcessId", wintypes.DWORD),
            ("dwThreadId", wintypes.DWORD),
        ]

    class JobObjectBasicLimitInformation(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", ctypes.c_int64),
            ("PerJobUserTimeLimit", ctypes.c_int64),
            ("LimitFlags", wintypes.DWORD),
            ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t),
            ("ActiveProcessLimit", wintypes.DWORD),
            ("Affinity", ctypes.c_size_t),
            ("PriorityClass", wintypes.DWORD),
            ("SchedulingClass", wintypes.DWORD),
        ]

    class IoCounters(ctypes.Structure):
        _fields_ = [
            ("ReadOperationCount", ctypes.c_uint64),
            ("WriteOperationCount", ctypes.c_uint64),
            ("OtherOperationCount", ctypes.c_uint64),
            ("ReadTransferCount", ctypes.c_uint64),
            ("WriteTransferCount", ctypes.c_uint64),
            ("OtherTransferCount", ctypes.c_uint64),
        ]

    class JobObjectExtendedLimitInformation(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", JobObjectBasicLimitInformation),
            ("IoInfo", IoCounters),
            ("ProcessMemoryLimit", ctypes.c_size_t),
            ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryUsed", ctypes.c_size_t),
            ("PeakJobMemoryUsed", ctypes.c_size_t),
        ]

    _configure_windows_functions(advapi32, kernel32, StartupInfo, ProcessInformation)
    token = handle_type()
    restricted_token = handle_type()
    integrity_sid = pointer_type()
    process_info = ProcessInformation()
    job = handle_type()
    stdout_handle = None
    stderr_handle = None
    stdin_handle = None
    assigned_to_job = False
    try:
        _check_windows(
            advapi32.OpenProcessToken(kernel32.GetCurrentProcess(), 0xF01FF, ctypes.byref(token))
        )
        _check_windows(
            advapi32.CreateRestrictedToken(
                token, 0x1, 0, None, 0, None, 0, None, ctypes.byref(restricted_token)
            )
        )
        _check_windows(
            advapi32.ConvertStringSidToSidW("S-1-16-4096", ctypes.byref(integrity_sid))
        )
        label = TokenMandatoryLabel(SidAndAttributes(integrity_sid, 0x20))
        label_size = advapi32.GetLengthSid(integrity_sid) + ctypes.sizeof(TokenMandatoryLabel)
        _check_windows(
            advapi32.SetTokenInformation(
                restricted_token, 25, ctypes.byref(label), label_size
            )
        )

        stdout_path.parent.mkdir(parents=True, exist_ok=True)
        stdout_handle = stdout_path.open("wb")
        stderr_handle = stderr_path.open("wb")
        stdin_handle = open(os.devnull, "rb")
        for stream in (stdout_handle, stderr_handle, stdin_handle):
            os.set_handle_inheritable(msvcrt_get_osfhandle(stream.fileno()), True)

        startup = StartupInfo()
        startup.cb = ctypes.sizeof(startup)
        startup.dwFlags = 0x00000100
        startup.hStdInput = handle_type(msvcrt_get_osfhandle(stdin_handle.fileno()))
        startup.hStdOutput = handle_type(msvcrt_get_osfhandle(stdout_handle.fileno()))
        startup.hStdError = handle_type(msvcrt_get_osfhandle(stderr_handle.fileno()))
        environment_block = ctypes.create_unicode_buffer(
            "\0".join(f"{key}={value}" for key, value in sorted(environment.items())) + "\0\0"
        )
        command_line = ctypes.create_unicode_buffer(subprocess.list2cmdline(list(command)))
        creation_flags = 0x00000400 | 0x00000200 | 0x08000000 | 0x00000004
        _check_windows(
            advapi32.CreateProcessAsUserW(
                restricted_token,
                None,
                command_line,
                None,
                None,
                True,
                creation_flags,
                environment_block,
                str(cwd),
                ctypes.byref(startup),
                ctypes.byref(process_info),
            )
        )
        job = kernel32.CreateJobObjectW(None, None)
        _check_windows(job)
        limits = JobObjectExtendedLimitInformation()
        limits.BasicLimitInformation.LimitFlags = 0x00002000
        _check_windows(
            kernel32.SetInformationJobObject(
                job, 9, ctypes.byref(limits), ctypes.sizeof(limits)
            )
        )
        _check_windows(kernel32.AssignProcessToJobObject(job, process_info.hProcess))
        assigned_to_job = True
        if kernel32.ResumeThread(process_info.hThread) == 0xFFFFFFFF:
            raise ctypes.WinError(ctypes.get_last_error())
        wait_result = kernel32.WaitForSingleObject(process_info.hProcess, timeout_seconds * 1000)
        timed_out = wait_result == 0x00000102
        if timed_out:
            kernel32.TerminateJobObject(job, 124)
            kernel32.WaitForSingleObject(process_info.hProcess, 5_000)
            return IsolatedProcessResult(124, True)
        if wait_result != 0:
            raise ctypes.WinError(ctypes.get_last_error())
        exit_code = wintypes.DWORD()
        _check_windows(kernel32.GetExitCodeProcess(process_info.hProcess, ctypes.byref(exit_code)))
        return IsolatedProcessResult(exit_code.value, False)
    except OSError as exc:
        if process_info.hProcess and not assigned_to_job:
            kernel32.TerminateProcess(process_info.hProcess, 127)
        return IsolatedProcessResult(127, False, str(exc))
    finally:
        for stream in (stdout_handle, stderr_handle, stdin_handle):
            if stream is not None:
                stream.close()
        for handle in (
            process_info.hThread,
            process_info.hProcess,
            job,
            restricted_token,
            token,
        ):
            if handle:
                kernel32.CloseHandle(handle)
        if integrity_sid:
            kernel32.LocalFree(integrity_sid)


def _configure_windows_functions(advapi32, kernel32, startup_info, process_information) -> None:
    from ctypes import wintypes

    handle_type = wintypes.HANDLE
    pointer_type = wintypes.LPVOID
    kernel32.GetCurrentProcess.restype = handle_type
    kernel32.CreateJobObjectW.argtypes = [pointer_type, wintypes.LPCWSTR]
    kernel32.CreateJobObjectW.restype = handle_type
    kernel32.SetInformationJobObject.argtypes = [
        handle_type, wintypes.INT, pointer_type, wintypes.DWORD
    ]
    kernel32.AssignProcessToJobObject.argtypes = [handle_type, handle_type]
    kernel32.WaitForSingleObject.argtypes = [handle_type, wintypes.DWORD]
    kernel32.GetExitCodeProcess.argtypes = [handle_type, ctypes.POINTER(wintypes.DWORD)]
    kernel32.TerminateJobObject.argtypes = [handle_type, wintypes.UINT]
    kernel32.ResumeThread.argtypes = [handle_type]
    kernel32.ResumeThread.restype = wintypes.DWORD
    kernel32.TerminateProcess.argtypes = [handle_type, wintypes.UINT]
    kernel32.CloseHandle.argtypes = [handle_type]
    kernel32.LocalFree.argtypes = [pointer_type]
    advapi32.OpenProcessToken.argtypes = [
        handle_type, wintypes.DWORD, ctypes.POINTER(handle_type)
    ]
    advapi32.CreateRestrictedToken.argtypes = [
        handle_type, wintypes.DWORD, wintypes.DWORD, pointer_type,
        wintypes.DWORD, pointer_type, wintypes.DWORD, pointer_type,
        ctypes.POINTER(handle_type),
    ]
    advapi32.ConvertStringSidToSidW.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(pointer_type)]
    advapi32.GetLengthSid.argtypes = [pointer_type]
    advapi32.GetLengthSid.restype = wintypes.DWORD
    advapi32.SetTokenInformation.argtypes = [
        handle_type, wintypes.DWORD, pointer_type, wintypes.DWORD
    ]
    advapi32.CreateProcessAsUserW.argtypes = [
        handle_type, wintypes.LPCWSTR, wintypes.LPWSTR, pointer_type, pointer_type,
        wintypes.BOOL, wintypes.DWORD, pointer_type, wintypes.LPCWSTR,
        ctypes.POINTER(startup_info), ctypes.POINTER(process_information),
    ]


def _check_windows(result) -> None:
    if not result:
        raise ctypes.WinError(ctypes.get_last_error())


def msvcrt_get_osfhandle(file_descriptor: int) -> int:
    import msvcrt

    return msvcrt.get_osfhandle(file_descriptor)


_LANDLOCK_WRITE_ACCESS = (
    (1 << 1)
    | (1 << 4)
    | (1 << 5)
    | (1 << 6)
    | (1 << 7)
    | (1 << 8)
    | (1 << 9)
    | (1 << 10)
    | (1 << 11)
    | (1 << 12)
)


def _linux_landlock_abi() -> int:
    if not sys.platform.startswith("linux"):
        return 0
    libc = ctypes.CDLL(None, use_errno=True)
    result = libc.syscall(444, -1, 0, 1)
    return int(result) if result >= 1 else 0


def _linux_isolation_backend() -> str | None:
    if not sys.platform.startswith("linux"):
        return None
    if _linux_landlock_abi() > 0:
        return "linux-landlock"
    if _linux_mount_namespace_usable():
        return "linux-user-mount-namespace"
    return None


def _linux_handled_access(abi: int) -> int:
    access = _LANDLOCK_WRITE_ACCESS
    if abi >= 2:
        access |= 1 << 13
    if abi >= 3:
        access |= 1 << 14
    return access


def _apply_linux_landlock(repository: Path, runtime: Path) -> None:
    libc = ctypes.CDLL(None, use_errno=True)
    abi = _linux_landlock_abi()
    if abi < 1:
        raise ExperimentalIsolationUnavailable("Linux Landlock is unavailable")

    class RulesetAttr(ctypes.Structure):
        _fields_ = [("handled_access_fs", ctypes.c_uint64)]

    class PathBeneathAttr(ctypes.Structure):
        _fields_ = [("allowed_access", ctypes.c_uint64), ("parent_fd", ctypes.c_int32)]

    handled = _linux_handled_access(abi)
    ruleset_attr = RulesetAttr(handled)
    ruleset_fd = libc.syscall(444, ctypes.byref(ruleset_attr), ctypes.sizeof(ruleset_attr), 0)
    if ruleset_fd < 0:
        raise OSError(ctypes.get_errno(), "landlock_create_ruleset failed")
    try:
        for allowed_root in (repository, runtime):
            root_fd = os.open(allowed_root, os.O_PATH | os.O_CLOEXEC)
            try:
                rule = PathBeneathAttr(handled, root_fd)
                if libc.syscall(445, ruleset_fd, 1, ctypes.byref(rule), 0) < 0:
                    raise OSError(ctypes.get_errno(), "landlock_add_rule failed")
            finally:
                os.close(root_fd)
        if libc.prctl(38, 1, 0, 0, 0) != 0:
            raise OSError(ctypes.get_errno(), "PR_SET_NO_NEW_PRIVS failed")
        if libc.syscall(446, ruleset_fd, 0) < 0:
            raise OSError(ctypes.get_errno(), "landlock_restrict_self failed")
    finally:
        os.close(ruleset_fd)


def _run_linux_landlock(
    command: Sequence[str],
    *,
    repository: Path,
    runtime: Path,
    cwd: Path,
    environment: Mapping[str, str],
    stdout_path: Path,
    stderr_path: Path,
    timeout_seconds: int,
) -> IsolatedProcessResult:
    stdout_path.parent.mkdir(parents=True, exist_ok=True)
    wrapper = [
        sys.executable,
        str(Path(__file__).resolve()),
        "--landlock-exec",
        str(repository),
        str(runtime),
        "--",
        *command,
    ]
    try:
        with stdout_path.open("wb") as stdout_handle, stderr_path.open("wb") as stderr_handle:
            process = subprocess.Popen(
                wrapper,
                cwd=str(cwd),
                env=dict(environment),
                stdin=subprocess.DEVNULL,
                stdout=stdout_handle,
                stderr=stderr_handle,
                start_new_session=True,
            )
            try:
                exit_code = process.wait(timeout=timeout_seconds)
                return IsolatedProcessResult(exit_code, False)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
                return IsolatedProcessResult(124, True)
    except OSError as exc:
        return IsolatedProcessResult(127, False, str(exc))


def _landlock_exec_main(arguments: list[str]) -> int:
    separator = arguments.index("--")
    repository = Path(arguments[0]).resolve()
    runtime = Path(arguments[1]).resolve()
    command = arguments[separator + 1 :]
    _apply_linux_landlock(repository, runtime)
    os.execvpe(command[0], command, os.environ)
    return 127


@lru_cache(maxsize=1)
def _linux_mount_namespace_usable() -> bool:
    if not sys.platform.startswith("linux"):
        return False
    unshare = shutil.which("unshare")
    if unshare is None:
        return False
    try:
        with tempfile.TemporaryDirectory(prefix="oss-remediation-namespace-probe-") as temporary:
            root = Path(temporary)
            repository = root / "repository"
            runtime = root / "runtime"
            protected = root / "protected"
            for directory in (repository, runtime, protected):
                directory.mkdir()
            (runtime / "temp").mkdir()
            (repository / "existing.txt").write_text("before\n", encoding="utf-8")
            (protected / "protected.txt").write_text("original\n", encoding="utf-8")
            command = _linux_mount_namespace_command(
                unshare,
                repository,
                runtime,
                [
                    sys.executable,
                    str(Path(__file__).resolve()),
                    "--namespace-probe-child",
                    str(repository),
                    str(runtime),
                    str(protected),
                ],
            )
            completed = subprocess.run(
                command,
                cwd=repository,
                env=os.environ.copy(),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=10,
                check=False,
            )
            return (
                completed.returncode == 0
                and (repository / "existing.txt").read_text(encoding="utf-8") == "changed\n"
                and (repository / "created.txt").read_text(encoding="utf-8") == "created\n"
                and (runtime / "temp" / "probe.txt").read_text(encoding="utf-8") == "runtime\n"
                and (repository / "mount-denied.txt").is_file()
                and (protected / "protected.txt").read_text(encoding="utf-8") == "original\n"
            )
    except (OSError, subprocess.SubprocessError, FileNotFoundError):
        return False


def _linux_mount_namespace_command(
    unshare: str,
    repository: Path,
    runtime: Path,
    command: Sequence[str],
) -> list[str]:
    return [
        unshare,
        "--user",
        "--map-root-user",
        "--mount",
        "--pid",
        "--fork",
        "--mount-proc",
        sys.executable,
        str(Path(__file__).resolve()),
        "--namespace-exec",
        str(repository),
        str(runtime),
        "--",
        *command,
    ]


def _run_linux_mount_namespace(
    command: Sequence[str],
    *,
    repository: Path,
    runtime: Path,
    cwd: Path,
    environment: Mapping[str, str],
    stdout_path: Path,
    stderr_path: Path,
    timeout_seconds: int,
) -> IsolatedProcessResult:
    unshare = shutil.which("unshare")
    if unshare is None or not _linux_mount_namespace_usable():
        return IsolatedProcessResult(126, False, "Linux mount namespace isolation is unavailable")
    return _run_linux_subprocess(
        _linux_mount_namespace_command(unshare, repository, runtime, command),
        cwd=cwd,
        environment=environment,
        stdout_path=stdout_path,
        stderr_path=stderr_path,
        timeout_seconds=timeout_seconds,
    )


def _run_linux_subprocess(
    command: Sequence[str],
    *,
    cwd: Path,
    environment: Mapping[str, str],
    stdout_path: Path,
    stderr_path: Path,
    timeout_seconds: int,
) -> IsolatedProcessResult:
    stdout_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with stdout_path.open("wb") as stdout_handle, stderr_path.open("wb") as stderr_handle:
            process = subprocess.Popen(
                command,
                cwd=str(cwd),
                env=dict(environment),
                stdin=subprocess.DEVNULL,
                stdout=stdout_handle,
                stderr=stderr_handle,
                start_new_session=True,
            )
            try:
                exit_code = process.wait(timeout=timeout_seconds)
                return IsolatedProcessResult(exit_code, False)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
                return IsolatedProcessResult(124, True)
    except OSError as exc:
        return IsolatedProcessResult(127, False, str(exc))


_MS_BIND = 4096
_MS_REC = 16384
_MS_PRIVATE = 1 << 18
_AT_FDCWD = -100
_AT_RECURSIVE = 0x8000
_MOUNT_ATTR_RDONLY = 0x1
_OPEN_TREE_CLONE = 0x1
_OPEN_TREE_CLOEXEC = 0x80000
_MOVE_MOUNT_F_EMPTY_PATH = 0x4
_SYS_OPEN_TREE = 428
_SYS_MOVE_MOUNT = 429
_SYS_MOUNT_SETATTR = 442


def _apply_linux_mount_namespace(repository: Path, runtime: Path) -> None:
    libc = ctypes.CDLL(None, use_errno=True)
    libc.mount.argtypes = [
        ctypes.c_char_p,
        ctypes.c_char_p,
        ctypes.c_char_p,
        ctypes.c_ulong,
        ctypes.c_void_p,
    ]
    libc.mount.restype = ctypes.c_int
    _mount(libc, None, Path("/"), _MS_REC | _MS_PRIVATE)
    writable_mounts: list[tuple[Path, int]] = []
    try:
        for writable in dict.fromkeys((repository.resolve(), runtime.resolve())):
            writable_mounts.append((writable, _clone_detached_mount(libc, writable)))
        _set_mount_readonly(libc, Path("/"), readonly=True, recursive=True)
        for writable, mount_fd in writable_mounts:
            _attach_detached_mount(libc, mount_fd, writable)
    finally:
        for _, mount_fd in writable_mounts:
            os.close(mount_fd)
    system_temp = Path("/tmp")
    if not _path_within(repository, system_temp) and not _path_within(runtime, system_temp):
        _mount(libc, runtime / "temp", system_temp, _MS_BIND)
        _set_mount_readonly(libc, system_temp, readonly=False)


def _path_within(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def _mount(libc, source: Path | None, target: Path, flags: int) -> None:
    source_bytes = os.fsencode(source) if source is not None else None
    if libc.mount(source_bytes, os.fsencode(target), None, flags, None) != 0:
        error = ctypes.get_errno()
        raise OSError(error, f"mount operation failed for {target}: {os.strerror(error)}")


def _clone_detached_mount(libc, source: Path) -> int:
    libc.syscall.restype = ctypes.c_long
    mount_fd = libc.syscall(
        _SYS_OPEN_TREE,
        _AT_FDCWD,
        ctypes.c_char_p(os.fsencode(source)),
        _OPEN_TREE_CLONE | _OPEN_TREE_CLOEXEC,
    )
    if mount_fd < 0:
        error = ctypes.get_errno()
        raise OSError(error, f"open_tree failed for {source}: {os.strerror(error)}")
    return int(mount_fd)


def _attach_detached_mount(libc, mount_fd: int, target: Path) -> None:
    libc.syscall.restype = ctypes.c_long
    result = libc.syscall(
        _SYS_MOVE_MOUNT,
        mount_fd,
        ctypes.c_char_p(b""),
        _AT_FDCWD,
        ctypes.c_char_p(os.fsencode(target)),
        _MOVE_MOUNT_F_EMPTY_PATH,
    )
    if result != 0:
        error = ctypes.get_errno()
        raise OSError(error, f"move_mount failed for {target}: {os.strerror(error)}")


def _set_mount_readonly(
    libc,
    target: Path,
    *,
    readonly: bool,
    recursive: bool = False,
) -> None:
    class MountAttr(ctypes.Structure):
        _fields_ = [
            ("attr_set", ctypes.c_uint64),
            ("attr_clr", ctypes.c_uint64),
            ("propagation", ctypes.c_uint64),
            ("userns_fd", ctypes.c_uint64),
        ]

    attributes = MountAttr()
    if readonly:
        attributes.attr_set = _MOUNT_ATTR_RDONLY
    else:
        attributes.attr_clr = _MOUNT_ATTR_RDONLY
    flags = _AT_RECURSIVE if recursive else 0
    result = libc.syscall(
        _SYS_MOUNT_SETATTR,
        _AT_FDCWD,
        os.fsencode(target),
        flags,
        ctypes.byref(attributes),
        ctypes.sizeof(attributes),
    )
    if result != 0:
        error = ctypes.get_errno()
        raise OSError(error, f"mount_setattr failed for {target}: {os.strerror(error)}")


def _drop_linux_namespace_privileges() -> None:
    libc = ctypes.CDLL(None, use_errno=True)
    for capability in range(64):
        result = libc.prctl(24, capability, 0, 0, 0)
        if result != 0 and ctypes.get_errno() not in {errno.EINVAL}:
            error = ctypes.get_errno()
            raise OSError(error, f"PR_CAPBSET_DROP failed: {os.strerror(error)}")
    if libc.prctl(28, 0xF, 0, 0, 0) != 0:
        error = ctypes.get_errno()
        raise OSError(error, f"PR_SET_SECUREBITS failed: {os.strerror(error)}")
    if libc.prctl(47, 4, 0, 0, 0) != 0 and ctypes.get_errno() not in {errno.EINVAL}:
        error = ctypes.get_errno()
        raise OSError(error, f"PR_CAP_AMBIENT_CLEAR_ALL failed: {os.strerror(error)}")
    if libc.prctl(38, 1, 0, 0, 0) != 0:
        error = ctypes.get_errno()
        raise OSError(error, f"PR_SET_NO_NEW_PRIVS failed: {os.strerror(error)}")

    class CapHeader(ctypes.Structure):
        _fields_ = [("version", ctypes.c_uint32), ("pid", ctypes.c_int)]

    class CapData(ctypes.Structure):
        _fields_ = [
            ("effective", ctypes.c_uint32),
            ("permitted", ctypes.c_uint32),
            ("inheritable", ctypes.c_uint32),
        ]

    header = CapHeader(0x20080522, 0)
    data = (CapData * 2)()
    if libc.capset(ctypes.byref(header), ctypes.byref(data)) != 0:
        error = ctypes.get_errno()
        raise OSError(error, f"capset failed: {os.strerror(error)}")


def _namespace_exec_main(arguments: list[str]) -> int:
    separator = arguments.index("--")
    repository = Path(arguments[0]).resolve()
    runtime = Path(arguments[1]).resolve()
    command = arguments[separator + 1 :]
    working_directory = Path.cwd()
    _apply_linux_mount_namespace(repository, runtime)
    os.chdir(working_directory)
    _drop_linux_namespace_privileges()
    os.execvpe(command[0], command, os.environ)
    return 127


def _namespace_probe_child(arguments: list[str]) -> int:
    repository = Path(arguments[0])
    runtime = Path(arguments[1])
    protected = Path(arguments[2])
    Path("existing.txt").write_text("changed\n", encoding="utf-8")
    Path("created.txt").write_text("created\n", encoding="utf-8")
    (runtime / "temp" / "probe.txt").write_text("runtime\n", encoding="utf-8")
    protected_write_failed = False
    try:
        (protected / "protected.txt").write_text("changed\n", encoding="utf-8")
    except OSError:
        protected_write_failed = True
    mount_target = repository / "mount-target"
    mount_target.mkdir()
    libc = ctypes.CDLL(None, use_errno=True)
    mount_failed = libc.mount(
        os.fsencode(protected), os.fsencode(mount_target), None, _MS_BIND, None
    ) != 0
    if mount_failed:
        (repository / "mount-denied.txt").write_text("denied\n", encoding="utf-8")
    nested_target = repository / "nested-root"
    nested_target.mkdir()
    unshare = shutil.which("unshare")
    nested = subprocess.run(
        [
            unshare,
            "--user",
            "--map-root-user",
            "--mount",
            sys.executable,
            str(Path(__file__).resolve()),
            "--namespace-nested-probe",
            str(nested_target),
            str(protected / "protected.txt"),
        ],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=5,
        check=False,
    ) if unshare is not None else None
    nested_escape_failed = nested is not None and nested.returncode in {10, 11, 12}
    return 0 if protected_write_failed and mount_failed and nested_escape_failed else 1


def _namespace_nested_probe(arguments: list[str]) -> int:
    target = Path(arguments[0])
    protected = Path(arguments[1])
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.mount(os.fsencode("/"), os.fsencode(target), None, _MS_BIND, None) != 0:
        return 10
    try:
        _set_mount_readonly(libc, target, readonly=False)
    except OSError:
        return 11
    escaped = target / protected.relative_to("/")
    try:
        escaped.write_text("changed\n", encoding="utf-8")
    except OSError:
        return 12
    return 0


if __name__ == "__main__" and len(sys.argv) > 1:
    if sys.argv[1] == "--landlock-exec":
        raise SystemExit(_landlock_exec_main(sys.argv[2:]))
    if sys.argv[1] == "--namespace-exec":
        raise SystemExit(_namespace_exec_main(sys.argv[2:]))
    if sys.argv[1] == "--namespace-probe-child":
        raise SystemExit(_namespace_probe_child(sys.argv[2:]))
    if sys.argv[1] == "--namespace-nested-probe":
        raise SystemExit(_namespace_nested_probe(sys.argv[2:]))
