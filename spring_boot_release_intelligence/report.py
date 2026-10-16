from __future__ import annotations

import html
import json
from pathlib import Path


TABLES = [
    ["Rank", "Spring Boot", "Original", "Addressed", "Remaining", "New", "Total", "Recommendation"],
    ["Spring Boot", "Severity", "Original", "Addressed", "Remaining", "New", "Total"],
    ["Dependency", "Control / ownership", "Boot {base} default", "Maven-selected",
     "Known fixed version", "{severity}"],
    ["Dependency", "Dependency Ownership", "Boot {base} selected", "Boot {selected} default",
     "Boot {selected} selected", "Known fixed version", "Base vulnerabilities",
     "New version vulnerabilities", "Outcome"],
]


def _e(value) -> str:
    return html.escape(str(value if value is not None else "—"))


def _count(counts: dict) -> int:
    return sum(counts.values())


def _finding_text(findings: list[dict]) -> str:
    counts = {}
    for item in findings:
        counts[item["severity"]] = counts.get(item["severity"], 0) + 1
    return ", ".join(f"{value} {key.title()}" for key, value in counts.items()) or "0"


def _list_text(values: list | None, empty: str = "None") -> str:
    return ", ".join(str(value) for value in (values or [])) or empty


def render_html(result: dict) -> str:
    base = result["application"]["original_spring_boot_version"]
    severities = result["execution"]["selected_severities"]
    releases = result["releases"]
    assessed = [item for item in releases if item["assessment_status"] == "COMPLETE"]
    selected = next((item for item in assessed if item.get("rank") == 1), assessed[0])
    dependencies = result["dependencies"]
    baseline = {item["coordinate"]: item for item in dependencies if item["release"] == base}
    by_release = {(item["release"], item["coordinate"]): item for item in dependencies}
    rows1 = [["—", f"{base} (Base)", _count(releases[0]["counts"]["original"]), "—",
              _count(releases[0]["counts"]["remaining"]), "—",
              _count(releases[0]["counts"]["total"]), "Baseline"]]
    for item in sorted(assessed[1:], key=lambda value: value["rank"]):
        rows1.append([item["rank"], item["version"], _count(item["counts"]["original"]),
                      _count(item["counts"]["addressed"]), _count(item["counts"]["remaining"]),
                      _count(item["counts"]["new"]), _count(item["counts"]["total"]),
                      item["recommendation"]])
    rows2 = []
    for item in assessed:
        for severity in severities:
            rows2.append([item["version"] + (" (Base)" if item["version"] == base else ""),
                          severity.title(), *[item["counts"][name][severity]
                          for name in ("original", "addressed", "remaining", "new", "total")]])
    rows3 = []
    for coordinate, dependency in sorted(baseline.items()):
        findings = dependency.get("findings", [])
        fixed = sorted({v for finding in findings for v in finding.get("fixed_versions", [])})
        rows3.append([coordinate, dependency["ownership"], dependency.get("boot_managed_default"),
                      dependency["selected_version"], ", ".join(fixed) or "Unknown",
                      *[sum(f["severity"] == severity for f in findings) for severity in severities]])
    def table(headers, rows, table_id):
        return (f'<table id="{table_id}"><thead><tr>' + ''.join(f'<th>{_e(x)}</th>' for x in headers) +
                '</tr></thead><tbody>' + ''.join('<tr>' + ''.join(f'<td>{_e(x)}</td>' for x in row) +
                '</tr>' for row in rows) + '</tbody></table>')
    headers3 = [heading.format(base=base) for heading in TABLES[2][:5]] + severities
    # Table 4 rows are also embedded for the lightweight selector.
    comparisons = {}
    for release in assessed[1:]:
        rows = []
        coordinates = sorted(set(baseline) | {d["coordinate"] for d in dependencies
                             if d["release"] == release["version"]})
        for coordinate in coordinates:
            before, after = baseline.get(coordinate), by_release.get((release["version"], coordinate))
            base_findings = before.get("findings", []) if before else []
            new_findings = after.get("findings", []) if after else []
            fixed = sorted({v for finding in base_findings for v in finding.get("fixed_versions", [])})
            if before and not after: outcome = "Removed"
            elif after and not before: outcome = "Introduced"
            elif base_findings and not new_findings: outcome = "Addressed"
            elif new_findings: outcome = "Remains" + (" — overridden" if "OVERRIDDEN" in after["ownership"] else "")
            else: outcome = "No selected findings"
            rows.append([coordinate, (after or before)["ownership"],
                         before["selected_version"] if before else "—",
                         after.get("boot_managed_default") if after else "—",
                         after["selected_version"] if after else "—",
                         ", ".join(fixed) or "Unknown", _finding_text(base_findings),
                         _finding_text(new_findings), outcome])
        comparisons[release["version"]] = rows
    selected_rows = comparisons.get(selected["version"], [])
    options = ''.join(f'<option value="{_e(v)}"' + (' selected' if v == selected["version"] else '') +
                      f'>{_e(v)}</option>' for v in comparisons)
    payload = json.dumps(comparisons, sort_keys=True).replace('<', '\\u003c')
    override = ''.join(f'<p class="note">{_e(note)}</p>' for note in result.get("override_notes", []))
    errors = ''.join(f'<li>{_e(x["release"])} / {_e(x["stage"])}: {_e(x["message"])}</li>'
                     for x in result.get("errors", []))
    details = ''.join(f'<details><summary>{_e(item.get("release"))} · {_e(item["package"])} · {_e(item["advisory_id"])}</summary>'
                      f'<p>Severity: {_e(item["severity"])}; fixed evidence: {_e(", ".join(item.get("fixed_versions", [])) or "Unknown")}; '
                      f'evidence: {_e(item.get("evidence_reference"))}</p></details>'
                      for item in result.get("findings", []))
    script = """<script>const DATA=JSON.parse(document.getElementById('comparison-data').textContent);
function pick(v){const b=document.querySelector('#table4 tbody');b.innerHTML='';for(const r of DATA[v]){const tr=document.createElement('tr');for(const x of r){const td=document.createElement('td');td.textContent=x??'—';tr.appendChild(td)}b.appendChild(tr)}const h=document.querySelectorAll('#table4 th');h[3].textContent=`Boot ${v} default`;h[4].textContent=`Boot ${v} selected`}</script>"""
    limitations = result.get("evidence", {}).get("limitations", [])
    coverage = result.get("evidence", {}).get("coverage", "Complete selected Maven inventory for each successfully assessed release")
    modules = result["execution"].get("discovered_modules", result["execution"].get("modules", []))
    requested = result["execution"].get("requested_releases", [])
    evaluated = result["execution"].get("evaluated_releases", [])
    metadata = f"""<section id="report-metadata"><h2>Assessment metadata</h2><dl>
<dt>Application / project</dt><dd>{_e(result['application'].get('project_id') or result['application']['project_path'])}</dd>
<dt>Original Spring Boot</dt><dd>{_e(base)}</dd>
<dt>Requested releases</dt><dd>{_e(_list_text(requested))}</dd>
<dt>Evaluated releases</dt><dd>{_e(_list_text(evaluated))}</dd>
<dt>Scanner</dt><dd>{_e(result['scanner']['provider'])} {_e(result['scanner'].get('version'))}</dd>
<dt>Maven modules</dt><dd>{_e(_list_text(modules, 'Root project only'))}</dd>
<dt>Active profiles</dt><dd>{_e(_list_text(result['execution'].get('profiles'), 'None'))}</dd>
<dt>Relevant scopes</dt><dd>{_e(_list_text(result['execution'].get('scopes')))}</dd>
<dt>Selected severities</dt><dd>{_e(_list_text(severities))}</dd>
<dt>Other severities</dt><dd>{_e(result['execution'].get('other_severities', 'Not recorded'))}</dd>
<dt>Assessment coverage</dt><dd>{_e(coverage)}</dd>
<dt>Snapshot comparability</dt><dd>{_e(result['scanner'].get('snapshot_comparable', 'Unknown'))}</dd>
<dt>Meaningful limitations</dt><dd>{_e('; '.join(limitations) or 'None recorded')}</dd>
</dl></section>"""
    return f"""<!doctype html><html><head><meta charset="utf-8"><title>Spring Boot Release Intelligence</title>
<style>body{{font:14px system-ui;margin:2rem;color:#17202a}}table{{border-collapse:collapse;width:100%;margin:1rem 0 2rem}}th,td{{border:1px solid #ccd1d1;padding:.45rem;text-align:left}}th{{background:#eef2f3}}.note{{background:#fff7d6;padding:.7rem}}details{{margin:.5rem 0}}</style></head><body>
<h1>Spring Boot Release Intelligence</h1>{metadata}
<p>Security-only ranking; compatibility is not validated. Status: {_e(result['status'])}</p>
<h2>Overall release comparison and ranking</h2>{table(TABLES[0], rows1, 'table1')}{override}
<h2>Severity breakdown</h2>{table(TABLES[1], rows2, 'table2')}
<h2>Original dependency snapshot</h2>{table(headers3, rows3, 'table3')}
<h2>Original vs selected Spring Boot release</h2><label>Evaluated release <select onchange="pick(this.value)">{options}</select></label>
{table([x.format(base=base, selected=selected['version']) for x in TABLES[3]], selected_rows, 'table4')}
<details><summary>Dependency and advisory evidence</summary>{details or '<p>No selected findings.</p>'}</details>
<details><summary>Errors and assessment gaps</summary><ul>{errors or '<li>None recorded</li>'}</ul></details>
<script id="comparison-data" type="application/json">{payload}</script>{script}</body></html>"""


def write_report(result: dict, path: Path) -> None:
    path.write_text(render_html(result), encoding="utf-8")
