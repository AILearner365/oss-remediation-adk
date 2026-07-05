from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class PatchPlanNormalizationError(Exception):
    """Raised when deterministic patch-plan normalization cannot run safely."""


def normalize_patch_plan_for_maven_declarations(workspace_root: str | Path, patch_plan_path: str | Path) -> dict[str, Any]:
    """Expand a PATCH_PLAN to cover all matching direct Maven declarations.

    The remediation planning agent is allowed to reason, but Maven declaration
    coverage must be deterministic. If a vulnerable dependency appears in more
    than one direct pom.xml declaration, all matching literal-version declarations
    must be patched to the selected fixed version. This prevents non-determinism
    where one LLM run patches only the root pom.xml while another patches both
    the root and a module pom.xml.

    Scope is intentionally narrow:
    * only PATCH decisions are normalized;
    * only literal <version>old</version> declarations are patched;
    * only pomEvidence snippets from the project analyzer report are used;
    * existing patch files are not duplicated.
    """
    workspace = Path(workspace_root)
    plan_path = _resolve_workspace_ref(workspace, patch_plan_path)
    plan = _read_json(plan_path)
    analyzer_path = _project_analyzer_path(workspace, plan)
    analyzer = _read_json(analyzer_path)
    pom_evidence = analyzer.get("pomEvidence", []) or []

    added_patches: list[dict[str, Any]] = []
    warnings: list[str] = []

    for decision in plan.get("vulnerabilityDecisions", []) or []:
        if decision.get("decision") != "PATCH":
            continue
        dependency = decision.get("dependency") or {}
        group_id = dependency.get("groupId")
        artifact_id = dependency.get("artifactId")
        old_version = dependency.get("currentVersion")
        new_version = decision.get("fixedVersionSelected")
        if not all([group_id, artifact_id, old_version, new_version]):
            continue

        patches = decision.setdefault("patches", [])
        existing_files = {str(patch.get("file")) for patch in patches if patch.get("file")}
        for evidence_index, evidence in enumerate(pom_evidence):
            file_name = str(evidence.get("file") or "")
            snippet = str(evidence.get("snippet") or "")
            if not file_name.endswith("pom.xml"):
                continue
            if file_name in existing_files:
                continue
            if not _snippet_matches_dependency(snippet, group_id, artifact_id, old_version):
                continue

            old_text = snippet
            new_text = snippet.replace(f"<version>{old_version}</version>", f"<version>{new_version}</version>", 1)
            if old_text == new_text:
                warnings.append(
                    f"Skipped {group_id}:{artifact_id} in {file_name}; literal old version was not replaceable."
                )
                continue

            patch = {
                "changeType": "DEPENDENCY_VERSION_VALUE",
                "evidenceReferences": [f"baseline/project-analyzer-report.json#/pomEvidence/{evidence_index}"],
                "expectedOccurrences": 1,
                "file": file_name,
                "newText": new_text,
                "newVersion": str(new_version),
                "oldText": old_text,
                "oldVersion": str(old_version),
                "patchId": _patch_id(decision, file_name, len(patches) + 1),
                "generatedBy": "DeterministicPatchPlanNormalizer",
            }
            patches.append(patch)
            existing_files.add(file_name)
            added_patches.append({
                "vulnerabilityId": decision.get("vulnerabilityId"),
                "dependency": f"{group_id}:{artifact_id}",
                "file": file_name,
                "oldVersion": str(old_version),
                "newVersion": str(new_version),
                "reason": "Additional matching Maven declaration found in project analyzer pomEvidence.",
            })

    if added_patches or warnings:
        normalization = plan.setdefault("deterministicNormalization", {})
        normalization["tool"] = "DeterministicPatchPlanNormalizer"
        normalization["addedPatchCount"] = len(added_patches)
        normalization["addedPatches"] = added_patches
        normalization["warnings"] = warnings
        plan.setdefault("warnings", [])
        if added_patches:
            plan["warnings"].append(
                "Deterministic normalization added missing Maven declaration patches for dependencies already selected by the planning agent."
            )
        plan_path.write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    return {
        "status": "SUCCESS",
        "patchPlanPath": str(plan_path),
        "addedPatchCount": len(added_patches),
        "addedPatches": added_patches,
        "warnings": warnings,
    }


def _snippet_matches_dependency(snippet: str, group_id: str, artifact_id: str, old_version: str) -> bool:
    return (
        f"<groupId>{group_id}</groupId>" in snippet
        and f"<artifactId>{artifact_id}</artifactId>" in snippet
        and f"<version>{old_version}</version>" in snippet
    )


def _patch_id(decision: dict[str, Any], file_name: str, sequence: int) -> str:
    vuln = str(decision.get("vulnerabilityId") or "vulnerability").lower().replace("_", "-")
    safe_file = file_name.replace("/", "-").replace(".", "-")
    return f"patch-{vuln}-{safe_file}-{sequence}"


def _project_analyzer_path(workspace: Path, plan: dict[str, Any]) -> Path:
    refs = plan.get("artifactReferences") or {}
    candidate = refs.get("projectAnalyzerReport") or "baseline/project-analyzer-report.json"
    return _resolve_workspace_ref(workspace, candidate)


def _resolve_workspace_ref(workspace: Path, value: str | Path) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return workspace / path


def _read_json(path: str | Path) -> dict[str, Any]:
    resolved = Path(path)
    if not resolved.exists():
        raise PatchPlanNormalizationError(f"Required JSON artifact not found: {resolved}")
    return json.loads(resolved.read_text(encoding="utf-8"))
