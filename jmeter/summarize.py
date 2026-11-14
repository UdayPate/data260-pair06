"""
Turns JMeter result files (.jtl, CSV) into the tables and the graph the assignment asks for (Lab 2, Part 5).

    python jmeter/summarize.py                       (from the repo root)
    python jmeter/summarize.py --results docs/lab2/jmeter/results --out docs/lab2/jmeter

Input:  <results>/<scenario>_<users>.jtl      e.g. login_100.jtl, job_search_300.jtl, assistant_20.jtl
Output: <out>/results.json, <out>/results.md, <out>/avg_response_vs_concurrency.svg, <out>/assistant_latency.svg

For every file: samples, average response time (ms), throughput (requests per second) and error rate. For the assistant also the
p50, p95 and p99 latency (the time within which 50, 95 and 99 percent of requests finished).

  throughput  = samples / (end of the last request - start of the first request), the way JMeter's own report counts it
  error rate  = samples with success=false / samples (a wrong HTTP status or a timeout counts as an error)
Requests whose label starts with SETUP or INFO (the sign-in of the other scenarios, a status peek) are left out of every number.
No external libraries are needed: the graphs are written as SVG by hand.
"""
import argparse
import csv
import json
import re
from pathlib import Path

SCENARIOS = ["login", "job_search", "apply", "events", "assistant"]
TITLES = {"login": "Login", "job_search": "Job search", "apply": "Application submission (202, Kafka)",
          "events": "Event search + registration", "assistant": "Assistant chat"}
COLORS = {"login": "#1f77b4", "job_search": "#2ca02c", "apply": "#d62728", "events": "#9467bd", "assistant": "#ff7f0e"}
SKIPPED_PREFIXES = ("SETUP", "INFO")
FILE_NAME = re.compile(r"^(?P<scenario>[a-z_]+)_(?P<users>\d+)\.jtl$")


def percentile(sorted_values, p):
    """The value below which p percent of the sorted values fall (linear interpolation)."""
    if not sorted_values:
        return 0.0
    k = (len(sorted_values) - 1) * p / 100.0
    low = int(k)
    high = min(low + 1, len(sorted_values) - 1)
    return sorted_values[low] + (sorted_values[high] - sorted_values[low]) * (k - low)


def summarize_file(path: Path) -> dict:
    """Numbers for one result file."""
    starts, ends, elapsed, errors = [], [], [], 0
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if row["label"].startswith(SKIPPED_PREFIXES):
                continue
            began, took = int(row["timeStamp"]), int(row["elapsed"])
            starts.append(began)
            ends.append(began + took)
            elapsed.append(took)
            errors += row["success"].strip().lower() != "true"
    if not elapsed:
        return {"samples": 0}
    seconds = max((max(ends) - min(starts)) / 1000.0, 0.001)
    elapsed.sort()
    return {"samples": len(elapsed), "avg_ms": round(sum(elapsed) / len(elapsed), 1), "min_ms": elapsed[0], "max_ms": elapsed[-1],
            "p50_ms": round(percentile(elapsed, 50), 1), "p95_ms": round(percentile(elapsed, 95), 1),
            "p99_ms": round(percentile(elapsed, 99), 1), "throughput_rps": round(len(elapsed) / seconds, 2),
            "error_pct": round(100.0 * errors / len(elapsed), 2), "duration_s": round(seconds, 1)}


def collect(results_dir: Path) -> dict:
    """{scenario: {users: numbers}} for every result file that is there."""
    found = {}
    for path in sorted(results_dir.glob("*.jtl")):
        match = FILE_NAME.match(path.name)
        if match:
            found.setdefault(match["scenario"], {})[int(match["users"])] = summarize_file(path)
    return found


# ---------------------------------------------------------------- the graphs (plain SVG)
def line_chart(title, x_label, y_label, series, width=720, height=420):
    """series = {name: (color, [(x, y), ...])}. A line chart with markers, axes, grid and a legend."""
    left, right, top, bottom = 70, 150, 40, 55
    plot_w, plot_h = width - left - right, height - top - bottom
    xs = sorted({x for _, pts in series.values() for x, _ in pts}) or [0, 1]
    y_max = max([y for _, pts in series.values() for _, y in pts] + [1]) * 1.1

    def px(x):
        return left + (plot_w * (xs.index(x) / max(len(xs) - 1, 1)))

    def py(y):
        return top + plot_h * (1 - y / y_max)

    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" '
           'font-family="Arial, sans-serif" font-size="12">',
           f'<rect width="{width}" height="{height}" fill="white"/>',
           f'<text x="{width / 2}" y="22" text-anchor="middle" font-size="15" font-weight="bold">{title}</text>']
    for i in range(6):                                              # horizontal grid and y labels
        value = y_max * i / 5
        y = py(value)
        out.append(f'<line x1="{left}" y1="{y:.1f}" x2="{left + plot_w}" y2="{y:.1f}" stroke="#dddddd"/>')
        out.append(f'<text x="{left - 8}" y="{y + 4:.1f}" text-anchor="end">{value:,.0f}</text>')
    for x in xs:                                                    # x labels
        out.append(f'<text x="{px(x):.1f}" y="{top + plot_h + 18}" text-anchor="middle">{x}</text>')
    out.append(f'<line x1="{left}" y1="{top + plot_h}" x2="{left + plot_w}" y2="{top + plot_h}" stroke="#333"/>')
    out.append(f'<line x1="{left}" y1="{top}" x2="{left}" y2="{top + plot_h}" stroke="#333"/>')
    out.append(f'<text x="{left + plot_w / 2}" y="{height - 10}" text-anchor="middle">{x_label}</text>')
    out.append(f'<text x="16" y="{top + plot_h / 2}" text-anchor="middle" transform="rotate(-90 16 {top + plot_h / 2})">{y_label}</text>')
    for index, (name, (color, points)) in enumerate(series.items()):
        points = sorted(points)
        path = " ".join(f"{px(x):.1f},{py(y):.1f}" for x, y in points)
        out.append(f'<polyline fill="none" stroke="{color}" stroke-width="2.5" points="{path}"/>')
        for x, y in points:
            out.append(f'<circle cx="{px(x):.1f}" cy="{py(y):.1f}" r="4" fill="{color}"/>')
        ly = top + 10 + index * 20                                  # legend
        out.append(f'<line x1="{width - right + 14}" y1="{ly}" x2="{width - right + 40}" y2="{ly}" stroke="{color}" stroke-width="2.5"/>')
        out.append(f'<text x="{width - right + 46}" y="{ly + 4}">{name}</text>')
    out.append("</svg>")
    return "\n".join(out)


def write_outputs(found: dict, out_dir: Path) -> str:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "results.json").write_text(json.dumps(found, indent=2), encoding="utf-8")

    crud = {name: (COLORS[name], [(u, v["avg_ms"]) for u, v in sorted(levels.items()) if v.get("samples")])
            for name, levels in found.items() if name != "assistant"}
    if any(pts for _, pts in crud.values()):
        (out_dir / "avg_response_vs_concurrency.svg").write_text(
            line_chart("Average response time vs concurrent users", "Concurrent users", "Average response time (ms)",
                       {TITLES[n]: v for n, v in crud.items()}), encoding="utf-8")
    chat = found.get("assistant", {})
    if chat:
        series = {label: (color, [(u, v[key]) for u, v in sorted(chat.items()) if v.get("samples")])
                  for label, color, key in (("p50", "#1f77b4", "p50_ms"), ("p95", "#ff7f0e", "p95_ms"), ("p99", "#d62728", "p99_ms"))}
        (out_dir / "assistant_latency.svg").write_text(
            line_chart("Assistant chat latency vs concurrent users", "Concurrent users", "Latency (ms)", series), encoding="utf-8")

    lines = ["# JMeter results", ""]
    for name in SCENARIOS:
        levels = found.get(name)
        if not levels:
            continue
        lines += [f"## {TITLES[name]}", ""]
        if name == "assistant":
            lines += ["| Users | Samples | p50 ms | p95 ms | p99 ms | Error rate |", "|---|---|---|---|---|---|"]
            lines += [f"| {u} | {v['samples']} | {v['p50_ms']} | {v['p95_ms']} | {v['p99_ms']} | {v['error_pct']}% |"
                      for u, v in sorted(levels.items()) if v.get("samples")]
        else:
            lines += ["| Users | Samples | Avg response ms | Throughput req/s | Error rate |", "|---|---|---|---|---|"]
            lines += [f"| {u} | {v['samples']} | {v['avg_ms']} | {v['throughput_rps']} | {v['error_pct']}% |"
                      for u, v in sorted(levels.items()) if v.get("samples")]
        lines.append("")
    text = "\n".join(lines)
    (out_dir / "results.md").write_text(text, encoding="utf-8")
    return text


def main():
    root = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser()
    parser.add_argument("--results", default=str(root / "docs" / "lab2" / "jmeter" / "results"))
    parser.add_argument("--out", default=str(root / "docs" / "lab2" / "jmeter"))
    args = parser.parse_args()
    found = collect(Path(args.results))
    if not found:
        print(f"No result files like login_100.jtl found in {args.results}")
        return 2
    print(write_outputs(found, Path(args.out)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
