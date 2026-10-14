from __future__ import annotations

import html
import json
from pathlib import Path


COLORS = ["#2563eb", "#16a34a", "#dc2626", "#ca8a04"]
STATUS_COLORS = {
    "PROVEN": "#16a34a", "PARTIALLY_PROVEN": "#ca8a04",
    "NOT_SUPPORTED": "#64748b", "FAILED": "#dc2626", "NOT_TESTED": "#cbd5e1",
}


def _svg(title: str, labels: list[str], series: list[tuple[str, list[float]]],
         note: str = "", unit: str = "") -> str:
    width, height = 900, 480
    left, top, bottom = 90, 65, 95
    plot_w, plot_h = width - left - 35, height - top - bottom
    maximum = max([value for _, values in series for value in values] or [1])
    maximum = maximum or 1
    group = plot_w / max(1, len(labels))
    bar_w = min(70, group * 0.75 / max(1, len(series)))
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
           '<rect width="100%" height="100%" fill="white"/>',
           f'<text x="{width/2}" y="30" text-anchor="middle" font-family="sans-serif" font-size="20">{html.escape(title)}</text>',
           f'<line x1="{left}" y1="{top+plot_h}" x2="{left+plot_w}" y2="{top+plot_h}" stroke="#334155"/>']
    for index, label in enumerate(labels):
        center = left + group * (index + 0.5)
        out.append(f'<text x="{center}" y="{top+plot_h+25}" text-anchor="middle" font-family="sans-serif" font-size="12">{html.escape(label)}</text>')
        for sidx, (name, values) in enumerate(series):
            value = values[index]
            h = plot_h * value / maximum
            x = center - len(series) * bar_w / 2 + sidx * bar_w
            y = top + plot_h - h
            out.extend([
                f'<rect x="{x}" y="{y}" width="{bar_w-3}" height="{h}" fill="{COLORS[sidx % len(COLORS)]}"/>',
                f'<text x="{x+(bar_w-3)/2}" y="{max(top+12,y-5)}" text-anchor="middle" font-family="sans-serif" font-size="11">{value:g}{html.escape(unit)}</text>'])
    legend_x = left
    for sidx, (name, _) in enumerate(series):
        out.extend([f'<rect x="{legend_x}" y="{height-42}" width="13" height="13" fill="{COLORS[sidx % len(COLORS)]}"/>',
                    f'<text x="{legend_x+18}" y="{height-31}" font-family="sans-serif" font-size="12">{html.escape(name)}</text>'])
        legend_x += 150
    if note:
        out.append(f'<text x="{left}" y="{height-10}" font-family="sans-serif" font-size="11" fill="#475569">{html.escape(note)}</text>')
    out.append("</svg>")
    return "\n".join(out)


def _capability(cells: list[dict]) -> str:
    approaches = [f"A{i}" for i in range(1, 6)]
    cases = [f"C{i}" for i in range(1, 5)]
    lookup = {(cell["approach"], cell["case"]): cell["status"] for cell in cells}
    out = ['<svg xmlns="http://www.w3.org/2000/svg" width="900" height="390">',
           '<rect width="100%" height="100%" fill="white"/>',
           '<text x="450" y="30" text-anchor="middle" font-family="sans-serif" font-size="20">A1–A5 capability coverage across C1–C4</text>']
    for col, case in enumerate(cases):
        out.append(f'<text x="{235+col*150}" y="70" text-anchor="middle" font-family="sans-serif">{case}</text>')
    for row, approach in enumerate(approaches):
        y = 90 + row * 52
        out.append(f'<text x="85" y="{y+25}" font-family="sans-serif" font-size="14">{approach}</text>')
        for col, case in enumerate(cases):
            status = lookup.get((approach, case), "NOT_TESTED")
            x = 160 + col * 150
            out.extend([f'<rect x="{x}" y="{y}" width="145" height="38" rx="4" fill="{STATUS_COLORS[status]}"/>',
                        f'<text x="{x+72.5}" y="{y+24}" text-anchor="middle" font-family="sans-serif" font-size="11" fill="white">{status}</text>'])
    out.append('<text x="30" y="375" font-family="sans-serif" font-size="11">A1–A4 are preserved v2 results; A5 is the 2026-10-14 execution.</text></svg>')
    return "\n".join(out)


def generate_a5_charts(results_file: Path, output_dir: Path) -> list[Path]:
    data = json.loads(results_file.read_text(encoding="utf-8"))
    output_dir.mkdir(parents=True, exist_ok=True)
    charts: dict[str, str] = {}
    charts["01-capability-coverage.svg"] = _capability(data["cells"])
    scenarios = list(data["a5"]["fresh"]["scenarios"])
    charts["02-expanded-accuracy.svg"] = _svg(
        "A2 vs A5 expanded Maven scenario accuracy", scenarios,
        [("A2", [int(data["a2_comparison_run"]["fresh"]["scenarios"][x]["passed"]) for x in scenarios]),
         ("A5", [int(data["a5"]["fresh"]["scenarios"][x]["passed"]) for x in scenarios])],
        "1 = expected version and path checks passed")
    releases = list(data["release_comparison"]["candidates"])
    summaries = [data["release_comparison"]["candidates"][x]["summary"] for x in releases]
    charts["03-addressed-by-release.svg"] = _svg(
        "Original findings addressed by Spring Boot release", releases,
        [("Addressed", [x["addressed"] for x in summaries])])
    charts["04-findings-by-release.svg"] = _svg(
        "Remaining, new, and unknown findings per release", releases,
        [("Remaining", [x["remaining"] for x in summaries]),
         ("New", [x["new"] for x in summaries]),
         ("Unknown", [x["unknown"] for x in summaries])])
    charts["05-fresh-warm-time.svg"] = _svg(
        "Fresh-cache vs warm-cache workload time", ["Fresh", "Warm"],
        [("A2", [round(data["a2_comparison_run"][x]["elapsed_seconds"], 1) for x in ("fresh", "warm")]),
         ("A5", [round(data["a5"][x]["elapsed_seconds"], 1) for x in ("fresh", "warm")])],
        "Same 16-resolution workload; elapsed seconds", "s")
    charts["06-cache-and-downloads.svg"] = _svg(
        "Fresh cache footprint and JAR types", ["Cache MB", "Application JARs", "Plugin JARs"],
        [("A2", [round(data["a2_comparison_run"]["fresh"]["storage"]["cache_bytes_after"]/1_000_000, 1),
                  data["a2_comparison_run"]["fresh"]["storage"]["binary_summary"]["application_dependency_jars"]["count"],
                  data["a2_comparison_run"]["fresh"]["storage"]["binary_summary"]["plugin_bootstrap_jars"]["count"]]),
         ("A5", [round(data["a5"]["fresh"]["storage"]["cache_bytes_after"]/1_000_000, 1),
                  data["a5"]["fresh"]["storage"]["binary_summary"]["application_dependency_jars"]["count"],
                  data["a5"]["fresh"]["storage"]["binary_summary"]["plugin_bootstrap_jars"]["count"]])],
        "Mixed units are labeled values; A5 attribution uses zero-dependency bootstrap control")
    transfers = data.get("network_telemetry", {}).get(
        "fresh_transfers", data["a5"]["fresh"]["storage"]["transfers"])
    charts["07-network-usage.svg"] = _svg(
        "Measured Maven transfer events and reported payload", ["Transfer events", "Reported MB"],
        [("A5", [transfers["successful_transfer_events"],
                 round(transfers["maven_reported_bytes"]/1_000_000, 2)])],
        "Separate non-quiet A5 telemetry; A2 and HTTP request counts unavailable; not used for timing")
    written = []
    for name, content in charts.items():
        path = output_dir / name
        path.write_text(content, encoding="utf-8")
        written.append(path)
    html_file = output_dir.parent / "a5-charts.html"
    html_file.write_text(
        "<!doctype html><meta charset='utf-8'><title>A5 comparison charts</title>"
        "<style>body{font:16px sans-serif;max-width:980px;margin:auto}img{max-width:100%;border:1px solid #ddd;margin:12px 0}</style>"
        "<h1>A5 evidence charts</h1><p>Generated from <code>results-a5.json</code>.</p>" +
        "".join(f"<h2>{html.escape(path.stem)}</h2><img src='charts/{path.name}' alt='{html.escape(path.stem)}'>"
                for path in written), encoding="utf-8")
    written.append(html_file)
    return written
