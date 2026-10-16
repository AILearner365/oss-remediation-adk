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


FILTER_SCRIPT = r"""<script>
(() => {
  const comparisonData = JSON.parse(document.getElementById('comparison-data').textContent);
  const controllers = new Map();
  let openMenu = null;
  let openButton = null;

  const closeMenu = () => {
    if (openMenu) openMenu.remove();
    if (openButton) openButton.setAttribute('aria-expanded', 'false');
    openMenu = null; openButton = null;
  };
  const cellValue = (row, column) => row.cells[column].textContent.trim();
  const numericColumn = (rows, column) => {
    const values = rows.map(row => cellValue(row, column)).filter(value => value !== '—');
    return values.length > 0 && values.every(value => value !== '' && Number.isFinite(Number(value)));
  };
  const compare = (left, right, numeric) => numeric
    ? Number(left) - Number(right)
    : left.localeCompare(right, undefined, {numeric: true, sensitivity: 'base'});

  class TableFilter {
    constructor(table) {
      this.table = table;
      this.body = table.tBodies[0];
      this.filters = new Map();
      this.sort = null;
      this.captureRows();
      this.decorateHeaders();
      this.addControls();
      this.render();
    }
    captureRows() {
      this.rows = Array.from(this.body.rows);
      this.rows.forEach((row, index) => { row.dataset.sourceIndex = String(index); });
    }
    decorateHeaders() {
      Array.from(this.table.tHead.rows[0].cells).forEach((header, column) => {
        const label = header.textContent;
        header.textContent = '';
        const span = document.createElement('span');
        span.className = 'header-label'; span.textContent = label;
        const button = document.createElement('button');
        button.type = 'button'; button.className = 'filter-button';
        button.dataset.column = String(column);
        button.setAttribute('aria-label', `Filter and sort ${label}`);
        button.setAttribute('aria-haspopup', 'dialog');
        button.setAttribute('aria-expanded', 'false');
        button.addEventListener('click', event => {
          event.stopPropagation(); this.open(column, button);
        });
        header.append(span, button);
      });
    }
    addControls() {
      const wrapper = this.table.closest('.table-region');
      const reset = wrapper.querySelector('.reset-filters');
      reset.addEventListener('click', () => this.reset());
      this.status = wrapper.querySelector('.row-count');
    }
    values(column) {
      return Array.from(new Set(this.rows.map(row => cellValue(row, column))))
        .sort((a, b) => compare(a, b, numericColumn(this.rows, column)));
    }
    open(column, button) {
      closeMenu();
      const values = this.values(column);
      const selected = this.filters.get(column) || new Set(values);
      const menu = document.createElement('div');
      menu.className = 'filter-menu'; menu.setAttribute('role', 'dialog');
      menu.setAttribute('aria-label', button.getAttribute('aria-label'));
      menu.innerHTML = `<div class="sort-actions"><button type="button" data-sort="asc">Sort ${numericColumn(this.rows, column) ? 'smallest to largest' : 'A–Z'}</button><button type="button" data-sort="desc">Sort ${numericColumn(this.rows, column) ? 'largest to smallest' : 'Z–A'}</button></div><label class="search-label">Search values<input type="search" class="filter-search" autocomplete="off"></label><div class="selection-actions"><button type="button" data-select="all">Select all</button><button type="button" data-select="none">Deselect all</button></div><div class="filter-values" role="group"></div><div class="menu-actions"><button type="button" data-action="clear">Clear Filter</button><button type="button" data-action="apply" class="primary">Apply</button></div>`;
      const list = menu.querySelector('.filter-values');
      values.forEach((value, index) => {
        const label = document.createElement('label'); label.className = 'filter-value';
        const checkbox = document.createElement('input'); checkbox.type = 'checkbox';
        checkbox.value = value; checkbox.checked = selected.has(value);
        checkbox.id = `${this.table.id}-c${column}-v${index}`;
        const text = document.createElement('span'); text.textContent = value;
        label.append(checkbox, text); list.append(label);
      });
      menu.querySelector('.filter-search').addEventListener('input', event => {
        const query = event.target.value.toLocaleLowerCase();
        list.querySelectorAll('.filter-value').forEach(label => {
          label.hidden = !label.textContent.toLocaleLowerCase().includes(query);
        });
      });
      menu.querySelectorAll('[data-sort]').forEach(action => action.addEventListener('click', () => {
        this.sort = {column, direction: action.dataset.sort}; this.render(); closeMenu();
      }));
      menu.querySelector('[data-select="all"]').addEventListener('click', () => {
        list.querySelectorAll('.filter-value:not([hidden]) input').forEach(input => { input.checked = true; });
      });
      menu.querySelector('[data-select="none"]').addEventListener('click', () => {
        list.querySelectorAll('.filter-value:not([hidden]) input').forEach(input => { input.checked = false; });
      });
      menu.querySelector('[data-action="clear"]').addEventListener('click', () => {
        this.filters.delete(column); this.render(); closeMenu();
      });
      menu.querySelector('[data-action="apply"]').addEventListener('click', () => {
        const chosen = new Set(Array.from(list.querySelectorAll('input:checked')).map(input => input.value));
        if (chosen.size === values.length) this.filters.delete(column);
        else this.filters.set(column, chosen);
        this.render(); closeMenu();
      });
      document.body.append(menu); openMenu = menu; openButton = button; button.setAttribute('aria-expanded', 'true');
      const rect = button.getBoundingClientRect();
      const width = Math.min(320, window.innerWidth - 16);
      menu.style.width = `${width}px`;
      menu.style.left = `${Math.max(8, Math.min(rect.left, window.innerWidth - width - 8))}px`;
      const below = rect.bottom + 4;
      menu.style.top = `${below + Math.min(420, menu.scrollHeight) > window.innerHeight
        ? Math.max(8, rect.top - Math.min(420, menu.scrollHeight) - 4) : below}px`;
      menu.querySelector('.filter-search').focus();
      menu.addEventListener('keydown', event => {
        if (event.key === 'Escape') { event.stopPropagation(); closeMenu(); button.focus(); }
      });
    }
    render() {
      let ordered = this.rows.map((row, index) => ({row, index}));
      if (this.sort) {
        const {column, direction} = this.sort; const numeric = numericColumn(this.rows, column);
        ordered.sort((a, b) => {
          const result = compare(cellValue(a.row, column), cellValue(b.row, column), numeric);
          return result === 0 ? a.index - b.index : (direction === 'asc' ? result : -result);
        });
      }
      let visible = 0;
      ordered.forEach(({row}) => {
        const show = Array.from(this.filters).every(([column, selected]) => selected.has(cellValue(row, column)));
        row.hidden = !show; if (show) visible += 1; this.body.append(row);
      });
      this.table.querySelectorAll('.filter-button').forEach(button => {
        button.classList.toggle('active', this.filters.has(Number(button.dataset.column)));
      });
      this.status.textContent = `Showing ${visible} of ${this.rows.length} rows`;
    }
    reset() { this.filters.clear(); this.sort = null; this.render(); closeMenu(); }
    replaceRows(rows) {
      this.body.textContent = '';
      rows.forEach(values => {
        const row = this.body.insertRow();
        values.forEach(value => { const cell = row.insertCell(); cell.textContent = value ?? '—'; });
      });
      this.filters.clear(); this.sort = null; this.captureRows(); this.render(); closeMenu();
    }
  }

  window.pick = version => {
    const table = document.getElementById('table4');
    const headers = table.tHead.rows[0].cells;
    headers[3].querySelector('.header-label').textContent = `Boot ${version} default`;
    headers[4].querySelector('.header-label').textContent = `Boot ${version} selected`;
    controllers.get('table4').replaceRows(comparisonData[version] || []);
  };
  document.querySelectorAll('table[data-filterable]').forEach(table => {
    controllers.set(table.id, new TableFilter(table));
  });
  window.SBRI_TABLES = controllers;
  document.addEventListener('click', event => {
    if (openMenu && !openMenu.contains(event.target) && !event.target.closest('.filter-button')) closeMenu();
  });
  document.addEventListener('keydown', event => { if (event.key === 'Escape') closeMenu(); });
})();
</script>"""


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
    def table(headers, rows, table_id, noun="rows"):
        return (f'<div class="table-region"><div class="table-controls"><button type="button" class="reset-filters">Reset All Filters</button>'
                f'<span class="row-count" aria-live="polite">Showing {len(rows)} of {len(rows)} {noun}</span></div><div class="table-scroll">'
                f'<table id="{table_id}" data-filterable="true"><thead><tr>' + ''.join(f'<th>{_e(x)}</th>' for x in headers) +
                '</tr></thead><tbody>' + ''.join('<tr>' + ''.join(f'<td>{_e(x)}</td>' for x in row) +
                '</tr>' for row in rows) + '</tbody></table></div></div>')
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
<style>body{{font:14px system-ui;margin:2rem;color:#17202a}}.table-region{{margin:1rem 0 2rem}}.table-controls{{display:flex;align-items:center;gap:.8rem;margin:.35rem 0}}.table-controls button,.filter-menu button{{font:inherit}}.row-count{{color:#52606d}}.table-scroll{{max-height:34rem;overflow:auto;border:1px solid #ccd1d1}}table{{border-collapse:separate;border-spacing:0;width:100%;min-width:max-content}}th,td{{border-right:1px solid #ccd1d1;border-bottom:1px solid #ccd1d1;padding:.45rem;text-align:left;max-width:32rem}}th{{background:#eef2f3;position:sticky;top:0;z-index:2;white-space:nowrap}}.header-label{{vertical-align:middle}}.filter-button{{margin-left:.35rem;width:1.45rem;height:1.45rem;border:1px solid transparent;border-radius:3px;background:transparent;color:#34495e;cursor:pointer}}.filter-button::before{{content:'▾'}}.filter-button:hover,.filter-button:focus{{border-color:#7f8c8d;background:#fff}}.filter-button.active{{background:#d6eaf8;border-color:#2471a3;color:#154360}}.filter-menu{{position:fixed;z-index:1000;box-sizing:border-box;max-height:420px;overflow:auto;padding:.65rem;background:#fff;border:1px solid #7f8c8d;border-radius:4px;box-shadow:0 5px 18px #0003}}.sort-actions,.selection-actions,.menu-actions{{display:flex;gap:.4rem;margin-bottom:.55rem}}.sort-actions{{flex-direction:column}}.menu-actions{{justify-content:flex-end;margin: .6rem 0 0}}.filter-menu button{{padding:.3rem .55rem;border:1px solid #aab7b8;border-radius:3px;background:#f7f9f9;cursor:pointer}}.filter-menu .primary{{background:#2471a3;color:white;border-color:#1f618d}}.search-label{{display:flex;flex-direction:column;gap:.25rem}}.filter-search{{box-sizing:border-box;width:100%;padding:.4rem}}.filter-values{{max-height:13rem;overflow:auto;border:1px solid #d5dbdb;margin-top:.4rem;padding:.3rem}}.filter-value{{display:flex;align-items:flex-start;gap:.4rem;padding:.2rem;overflow-wrap:anywhere}}.note{{background:#fff7d6;padding:.7rem}}details{{margin:.5rem 0}}</style></head><body>
<h1>Spring Boot Release Intelligence</h1>{metadata}
<p>Security-only ranking; compatibility is not validated. Status: {_e(result['status'])}</p>
<h2>Overall release comparison and ranking</h2>{table(TABLES[0], rows1, 'table1', 'releases')}{override}
<h2>Severity breakdown</h2>{table(TABLES[1], rows2, 'table2')}
<h2>Original dependency snapshot</h2>{table(headers3, rows3, 'table3', 'dependencies')}
<h2>Original vs selected Spring Boot release</h2><label>Evaluated release <select onchange="pick(this.value)">{options}</select></label>
{table([x.format(base=base, selected=selected['version']) for x in TABLES[3]], selected_rows, 'table4', 'dependencies')}
<details><summary>Dependency and advisory evidence</summary>{details or '<p>No selected findings.</p>'}</details>
<details><summary>Errors and assessment gaps</summary><ul>{errors or '<li>None recorded</li>'}</ul></details>
<script id="comparison-data" type="application/json">{payload}</script>{FILTER_SCRIPT}</body></html>"""


def write_report(result: dict, path: Path) -> None:
    path.write_text(render_html(result), encoding="utf-8")
