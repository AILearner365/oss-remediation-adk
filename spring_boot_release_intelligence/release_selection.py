"""Reusable, metadata-backed Spring Boot release candidate selection."""

from __future__ import annotations

import hashlib
import re
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Any, Callable


BOOT_METADATA = (
    "https://repo.maven.apache.org/maven2/org/springframework/boot/"
    "spring-boot-dependencies/maven-metadata.xml"
)
STABLE_VERSION = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")
RANGE = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.x$")
DEFAULT_MAX_CANDIDATES = 12


class ReleaseSelectionError(ValueError):
    """An actionable invalid release-selection request."""


@dataclass(frozen=True)
class Metadata:
    versions: tuple[str, ...]
    source: str
    sha256: str


def load_metadata() -> Metadata:
    with urllib.request.urlopen(BOOT_METADATA, timeout=30) as response:
        raw = response.read()
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as error:
        raise ReleaseSelectionError(f"invalid Spring Boot Maven metadata: {error}") from error
    versions = tuple(node.text.strip() for node in root.findall(".//version")
                     if node.text and node.text.strip())
    return Metadata(versions, BOOT_METADATA, hashlib.sha256(raw).hexdigest())


def _csv(value: str | list[str] | None) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, (str, list)):
        raise ReleaseSelectionError("release versions/ranges must be a comma-separated string or list")
    values = value if isinstance(value, list) else value.split(",")
    return [str(item).strip() for item in values if str(item).strip()]


def _version(value: str, label: str = "version") -> tuple[int, int, int]:
    match = STABLE_VERSION.fullmatch(value)
    if not match:
        raise ReleaseSelectionError(
            f"invalid {label} {value!r}; expected a stable numeric version such as 4.1.1"
        )
    return tuple(map(int, match.groups()))


def config_selection(config: dict[str, Any]) -> tuple[str | None, Any, int | None]:
    """Read the documented nested policy plus backward-compatible top-level keys."""
    nested = config.get("release_selection", {})
    if nested is None:
        nested = {}
    if not isinstance(nested, dict):
        raise ReleaseSelectionError("config release_selection must be an object")
    versions = nested.get("versions", config.get("releases"))
    ranges = nested.get("ranges", nested.get("range", config.get("range")))
    automatic = nested.get("automatic", False)
    supplied = [("versions", versions), ("range", ranges)]
    supplied = [(mode, value) for mode, value in supplied if _csv(value)]
    if automatic and supplied:
        raise ReleaseSelectionError("config release_selection cannot combine automatic with versions/ranges")
    if len(supplied) > 1:
        raise ReleaseSelectionError("config release_selection must specify only versions or ranges")
    maximum = nested.get("max_candidates", config.get("max_candidates"))
    if maximum is not None and (isinstance(maximum, bool) or not isinstance(maximum, int) or maximum < 1):
        raise ReleaseSelectionError("max_candidates must be a positive integer")
    if supplied:
        return supplied[0][0], supplied[0][1], maximum
    return ("automatic" if automatic else None), None, maximum


def select_candidates(
    baseline: str,
    *,
    versions: str | list[str] | None = None,
    ranges: str | list[str] | None = None,
    config: dict[str, Any] | None = None,
    max_candidates: int | None = None,
    metadata_loader: Callable[[], Metadata] = load_metadata,
    automatic_limit: int = 3,
) -> tuple[list[str], dict[str, Any]]:
    """Resolve one selection source and validate candidates against Maven metadata."""
    baseline_key = _version(baseline, "baseline version")
    configured_mode, configured_value, configured_max = config_selection(config or {})
    cli_sources = [("explicit", versions), ("range", ranges)]
    cli_sources = [(mode, value) for mode, value in cli_sources if _csv(value)]
    if len(cli_sources) > 1:
        raise ReleaseSelectionError("conflicting release selection: use only --sbri-versions or --sbri-range")
    if cli_sources and configured_mode is not None:
        raise ReleaseSelectionError(
            "conflicting release selection: CLI selection cannot be combined with config release_selection"
        )
    if max_candidates is not None and configured_max is not None and max_candidates != configured_max:
        raise ReleaseSelectionError("conflicting candidate limits in CLI and configuration")
    maximum = (max_candidates if max_candidates is not None else
               configured_max if configured_max is not None else DEFAULT_MAX_CANDIDATES)
    if isinstance(maximum, bool) or not isinstance(maximum, int) or maximum < 1:
        raise ReleaseSelectionError("max_candidates must be a positive integer")

    if cli_sources:
        mode, requested = cli_sources[0]
        source = "cli"
    elif configured_mode:
        mode, requested, source = configured_mode, configured_value, "config"
        if mode == "versions":
            mode = "explicit"
    else:
        mode, requested, source = "automatic", None, "automatic"

    metadata = metadata_loader()
    published = set(metadata.versions)
    stable_published = sorted((value for value in published if STABLE_VERSION.fullmatch(value)),
                              key=lambda value: tuple(map(int, value.split("."))))
    excluded: list[dict[str, str]] = []

    if mode == "explicit":
        requested_values = list(dict.fromkeys(_csv(requested)))
        if not requested_values:
            raise ReleaseSelectionError("explicit versions must contain at least one version")
        for value in requested_values:
            _version(value)
            if value not in published:
                raise ReleaseSelectionError(
                    f"requested Spring Boot version {value!r} is not present in authoritative Maven metadata"
                )
            if _version(value) <= baseline_key:
                raise ReleaseSelectionError(
                    f"requested Spring Boot version {value!r} is not newer than baseline {baseline}"
                )
        candidates = sorted(requested_values, key=lambda value: tuple(map(int, value.split("."))))
        requested_record: Any = requested_values
    elif mode == "range":
        requested_ranges = list(dict.fromkeys(_csv(requested)))
        if not requested_ranges:
            raise ReleaseSelectionError("release range must contain at least one range")
        keys = []
        intervals = []
        for value in requested_ranges:
            match = RANGE.fullmatch(value)
            if match:
                keys.append(tuple(map(int, match.groups())))
                continue
            if ".." in value:
                lower, upper = value.split("..", 1)
                lower_key, upper_key = _version(lower, "range lower bound"), _version(upper, "range upper bound")
                if lower_key > upper_key:
                    raise ReleaseSelectionError(f"release range lower bound exceeds upper bound: {value!r}")
                intervals.append((lower_key, upper_key))
                continue
            else:
                raise ReleaseSelectionError(
                    f"invalid release range {value!r}; expected major.minor.x or LOWER..UPPER"
                )
        candidates = [value for value in stable_published
                      if (_version(value)[:2] in keys or
                          any(lower <= _version(value) <= upper for lower, upper in intervals))
                      and _version(value) > baseline_key]
        requested_record = requested_ranges
        if not candidates:
            raise ReleaseSelectionError(
                f"no stable published forward releases match requested range(s) {','.join(requested_ranges)}"
            )
    else:
        major_minor = baseline_key[:2]
        eligible = [value for value in stable_published
                    if _version(value)[:2] == major_minor and _version(value) > baseline_key]
        candidates = eligible[-automatic_limit:]
        requested_record = [f"{major_minor[0]}.{major_minor[1]}.x"]
        if not candidates:
            raise ReleaseSelectionError(
                f"no stable published forward patch releases exist after baseline {baseline}"
            )

    if len(candidates) > maximum:
        raise ReleaseSelectionError(
            f"release selection matched {len(candidates)} candidates, exceeding max_candidates={maximum}; "
            "narrow the range, increase --sbri-max-candidates, or use --sbri-versions"
        )
    selection = {
        "mode": mode,
        "source": source,
        "requested": requested_record,
        "resolved_candidates": candidates,
        "candidate_count": len(candidates),
        "max_candidates": maximum,
        "excluded": excluded,
        "metadata": {"source": metadata.source, "sha256": metadata.sha256},
        "prereleases_allowed": False,
    }
    return candidates, selection
