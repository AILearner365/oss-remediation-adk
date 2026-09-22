from __future__ import annotations

import ctypes
import os
import signal
import subprocess
import sys
from dataclasses import dataclass
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
        return os.name == "nt" or (sys.platform.startswith("linux") and _linux_landlock_abi() > 0)

    @property
    def backend(self) -> str:
        if os.name == "nt":
            return "windows-low-integrity"
        if sys.platform.startswith("linux") and _linux_landlock_abi() > 0:
            return "linux-landlock"
        return "unavailable"

    def prepare(self, repository: Path, cycle: int, historical_repositories: Sequence[Path]) -> Path:
        if not self.available:
            raise ExperimentalIsolationUnavailable(
                "Experimental shell isolation requires Windows mandatory integrity control or Linux Landlock"
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


if __name__ == "__main__" and len(sys.argv) > 1 and sys.argv[1] == "--landlock-exec":
    raise SystemExit(_landlock_exec_main(sys.argv[2:]))
