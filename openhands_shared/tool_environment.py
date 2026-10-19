"""Credential-free deterministic tool environment, including Cloud Shell Maven."""
import os
from pathlib import Path
import shutil


def tool_environment(home: Path) -> dict[str, str]:
    paths = os.defpath.split(os.pathsep)
    for name in ("mvn", "java"):
        executable = shutil.which(name)
        if executable:
            parent = str(Path(executable).resolve().parent)
            if parent not in paths:
                paths.append(parent)
    return {"PATH": os.pathsep.join(paths), "HOME": str(home),
        "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8", "MAVEN_OPTS": "-Xmx512m"}
