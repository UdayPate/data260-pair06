"""
Builds LabPair-06_Lab2_Report.pdf (repository root) from docs/report/lab2_report.md.

    python docs/report/build_pdf.py              # run from the repository root (any Python 3, standard library only)
    python docs/report/build_pdf.py --redraw     # also draw the three architecture diagrams again

lab2_report.md is the single source of truth: edit it, run this script again. Steps:
  1. The diagrams. docs/lab2/ARCHITECTURE.md holds three Mermaid diagrams. Edge (headless) loads Mermaid, draws each one
     and the resulting SVG is saved in docs/report/img/ (these files are committed). This needs the internet ONCE (Mermaid
     is fetched from a CDN) and only when an SVG is missing or --redraw is given.
  2. The Markdown is turned into one HTML page by the small converter below (only the Markdown features the report uses).
  3. Edge (headless) prints that page to PDF. Microsoft Edge is installed with Windows; Chrome works too.
The Lab 1 report went Markdown -> LaTeX -> PDF with build_tex.py; LaTeX is not installed on this machine, so this build uses
the browser instead. The source format (Markdown, one file) is the same.
"""
import html
import os
import re
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SOURCE = HERE / "lab2_report.md"
IMG = HERE / "img"
ARCH = ROOT / "docs" / "lab2" / "ARCHITECTURE.md"
OUT = ROOT / "LabPair-06_Lab2_Report.pdf"
DIAGRAM_NAMES = ["architecture_containers", "architecture_apply_sequence", "architecture_kubernetes"]
MERMAID_URL = "https://cdn.jsdelivr.net/npm/mermaid@10.9.3/dist/mermaid.esm.min.mjs"

BROWSERS = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    "/mnt/c/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
    "/mnt/c/Program Files/Google/Chrome/Application/chrome.exe",
]


def find_browser() -> str:
    for candidate in BROWSERS:
        if os.path.exists(candidate):
            return candidate
    sys.exit("No Edge or Chrome found: install one of them or add its path to BROWSERS in build_pdf.py")


def run_browser(*args: str, timeout: int = 180) -> subprocess.CompletedProcess:
    cmd = [find_browser(), "--headless=new", "--disable-gpu", "--no-first-run", *args]
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, encoding="utf-8", errors="replace")


# ---------------------------------------------------------------------------------------------- 1. diagrams
def mermaid_blocks() -> list:
    text = ARCH.read_text(encoding="utf-8")
    return re.findall(r"```mermaid\n(.*?)```", text, flags=re.S)


def draw_diagram(source: str, target: Path) -> None:
    page = f"""<!doctype html><html><body style="margin:0;background:white">
<pre class="mermaid" id="d">{html.escape(source)}</pre>
<script type="module">
import mermaid from "{MERMAID_URL}";
mermaid.initialize({{startOnLoad: false, theme: "neutral", securityLevel: "loose",
  flowchart: {{htmlLabels: false, useMaxWidth: false, curve: "basis"}}, sequence: {{useMaxWidth: false, width: 125, actorMargin: 22, messageMargin: 30, boxMargin: 6}}}});
await mermaid.run({{querySelector: "#d"}});
document.body.setAttribute("data-done", "yes");
</script></body></html>"""
    with tempfile.TemporaryDirectory() as folder:
        temp = Path(folder) / "diagram.html"
        temp.write_text(page, encoding="utf-8")
        done = run_browser("--virtual-time-budget=30000", "--dump-dom", temp.as_uri())
    dom = done.stdout
    found = re.search(r"<svg.*?</svg>", dom, flags=re.S)
    if 'data-done="yes"' not in dom or not found:
        sys.exit(f"Mermaid did not draw {target.name} (is the internet reachable?)\n{done.stderr[-500:]}")
    svg = found.group(0)
    svg = svg.replace("<br>", "<br/>")
    ET.fromstring(svg)                                  # must be valid XML to be used as an image file
    target.write_text(svg, encoding="utf-8")


def ensure_diagrams(redraw: bool) -> None:
    blocks = mermaid_blocks()
    if len(blocks) != len(DIAGRAM_NAMES):
        sys.exit(f"{ARCH.name} has {len(blocks)} Mermaid diagrams, expected {len(DIAGRAM_NAMES)}")
    IMG.mkdir(exist_ok=True)
    for name, source in zip(DIAGRAM_NAMES, blocks):
        target = IMG / f"{name}.svg"
        if redraw or not target.exists():
            print(f"drawing {target.name} ...")
            draw_diagram(source, target)


# ---------------------------------------------------------------------------------------------- 2. Markdown -> HTML
def inline(text: str) -> str:
    text = html.escape(text, quote=False)
    text = re.sub(r"`([^`]+)`", lambda m: f"<code>{m.group(1)}</code>", text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"(?<![\w*])\*([^*\n]+)\*(?![\w*])", r"<em>\1</em>", text)
    text = re.sub(r"\[([^\]]+)\]\((https?://[^)]+)\)", r'<a href="\2">\1</a>', text)
    return text


def table_html(rows: list) -> str:
    def cells(line: str) -> list:
        line = line.strip().strip("|")
        return [c.strip() for c in re.split(r"(?<!\\)\|", line)]
    head, align = cells(rows[0]), cells(rows[1])
    right = [c.endswith(":") and not c.startswith(":") for c in align]
    out = [f'<table class="{"small" if len(rows) <= 13 else ""}"><thead><tr>']
    out += [f'<th class="{"r" if right[i] else ""}">{inline(c)}</th>' for i, c in enumerate(head)]
    out.append("</tr></thead><tbody>")
    for row in rows[2:]:
        out.append("<tr>" + "".join(f'<td class="{"r" if i < len(right) and right[i] else ""}">{inline(c.replace(chr(92) + "|", "|"))}</td>'
                                    for i, c in enumerate(cells(row))) + "</tr>")
    out.append("</tbody></table>")
    return "".join(out)


def markdown_to_html(md: str) -> str:
    md = re.sub(r"<!--.*?-->", "", md, flags=re.S)
    lines, out, i, figure = md.splitlines(), [], 0, 0
    while i < len(lines):
        line = lines[i]
        if not line.strip():
            i += 1
        elif line.startswith("```"):
            i += 1
            block = []
            while i < len(lines) and not lines[i].startswith("```"):
                block.append(lines[i])
                i += 1
            i += 1
            out.append("<pre><code>" + html.escape("\n".join(block)) + "</code></pre>")
        elif re.match(r"#{1,4} ", line):
            level = len(line.split(" ")[0])
            out.append(f"<h{level}>{inline(line[level + 1:])}</h{level}>")
            i += 1
        elif line.startswith("|"):
            rows = []
            while i < len(lines) and lines[i].startswith("|"):
                rows.append(lines[i])
                i += 1
            out.append(table_html(rows))
        elif re.match(r"!\[.*\]\(.*\)\s*$", line):
            caption, path = re.match(r"!\[(.*)\]\((.*)\)", line).groups()
            wide = path.endswith(' "wide"')                      # ![caption](file.svg "wide")  ->  own landscape page
            path = path.replace(' "wide"', "")
            figure += 1
            source = (HERE / path).resolve()
            out.append(f'<figure class="{"wide" if wide else ""}"><img src="{source.as_uri()}" alt="{html.escape(caption)}"><figcaption>Figure {figure}: {inline(caption)}</figcaption></figure>')
            i += 1
        elif line.startswith(">"):
            block = []
            while i < len(lines) and lines[i].startswith(">"):
                block.append(lines[i][1:].strip())
                i += 1
            css = "placeholder" if block[0].lstrip("*").startswith("PLACEHOLDER") else "note"
            out.append(f'<blockquote class="{css}">' + "".join(f"<p>{inline(b)}</p>" for b in block if b) + "</blockquote>")
        elif re.match(r"(- |\* )", line) or re.match(r"\d+\. ", line):
            ordered = bool(re.match(r"\d+\. ", line))
            items = []
            while i < len(lines) and (re.match(r"(- |\* )", lines[i]) or re.match(r"\d+\. ", lines[i]) or lines[i].startswith("  ")):
                if lines[i].startswith("  "):
                    items[-1] += " " + lines[i].strip()
                else:
                    items.append(re.sub(r"^(- |\* |\d+\. )", "", lines[i]))
                i += 1
            tag = "ol" if ordered else "ul"
            out.append(f"<{tag}>" + "".join(f"<li>{inline(x)}</li>" for x in items) + f"</{tag}>")
        else:
            para = []
            while i < len(lines) and lines[i].strip() and not re.match(r"(#|\||```|>|!\[|- |\* |\d+\. )", lines[i]):
                para.append(lines[i].strip())
                i += 1
            text = " ".join(para)
            lead = bool(re.fullmatch(r"\*\*[^*]+\*\*", text))          # a paragraph that is only a bold title stays with what follows
            out.append(f'<p class="{"lead" if lead else ""}">' + inline(text) + "</p>")
    return "\n".join(out)


CSS = """
@page { size: Letter; margin: 0.8in 0.8in 0.9in 0.8in; }
body { font-family: "Segoe UI", Calibri, Arial, sans-serif; font-size: 10pt; line-height: 1.42; color: #1b1b1b; }
h1 { font-size: 21pt; margin: 0 0 4pt; }
h2 { font-size: 14.5pt; margin: 20pt 0 6pt; padding-bottom: 2pt; border-bottom: 1.2px solid #444; break-after: avoid; }
h3 { font-size: 11.5pt; margin: 13pt 0 4pt; break-after: avoid; }
h4 { font-size: 10pt; margin: 10pt 0 3pt; break-after: avoid; }
p { margin: 4pt 0 6pt; }
ul, ol { margin: 3pt 0 7pt 0; padding-left: 18pt; } li { margin: 1.5pt 0; }
code { font-family: Consolas, "Cascadia Mono", monospace; font-size: 8.6pt; background: #f1f1f1; padding: 0 2pt; border-radius: 2px; overflow-wrap: anywhere; }
pre { font-family: Consolas, "Cascadia Mono", monospace; font-size: 7.4pt; line-height: 1.3; background: #f6f6f6; border: 0.5px solid #bbb; padding: 5pt 6pt;
      white-space: pre-wrap; overflow-wrap: anywhere; break-inside: avoid; margin: 5pt 0 8pt; }
pre code { background: none; padding: 0; font-size: inherit; }
table { border-collapse: collapse; width: 100%; margin: 5pt 0 9pt; font-size: 8.8pt; break-inside: auto; }
th, td { border: 0.5px solid #999; padding: 2.5pt 5pt; vertical-align: top; text-align: left; overflow-wrap: break-word; }
td code { overflow-wrap: break-word; }
th { background: #e9edf2; } tr { break-inside: avoid; } td.r, th.r { text-align: right; }
table.small { break-inside: avoid; }
p.lead { break-after: avoid; }
p:has(+ table.small), p:has(+ pre) { break-after: avoid; }      /* a lead-in sentence stays with its table */
figure { margin: 8pt 0 10pt; text-align: center; break-inside: avoid; }
figure img { max-width: 100%; max-height: 8.2in; }
@page wide { size: Letter landscape; margin: 0.55in; }
figure.wide { page: wide; margin: 0; }
figure.wide img { width: 100%; max-height: 6.7in; object-fit: contain; }
figcaption { font-size: 8.6pt; color: #444; margin-top: 3pt; }
blockquote { margin: 7pt 0; padding: 4pt 9pt; break-inside: avoid; }
blockquote p { margin: 2pt 0; }
blockquote.note { border-left: 3px solid #2f6f9f; background: #eef5fa; }
blockquote.placeholder { border: 1.5px dashed #b03030; background: #fdf1f1; }
.meta { color: #333; margin-bottom: 8pt; }
a { color: #1a4f8a; text-decoration: none; }
"""


def build_html(body: str) -> str:
    return f'<!doctype html><html><head><meta charset="utf-8"><title>DATA-260 Lab 2 Report, Pair 06</title><style>{CSS}</style></head><body>{body}</body></html>'


# ---------------------------------------------------------------------------------------------- 3. HTML -> PDF
def main() -> None:
    ensure_diagrams("--redraw" in sys.argv)
    page = build_html(markdown_to_html(SOURCE.read_text(encoding="utf-8")))
    with tempfile.TemporaryDirectory() as folder:
        temp = Path(folder) / "lab2_report.html"
        temp.write_text(page, encoding="utf-8")
        if OUT.exists():
            OUT.unlink()
        done = run_browser("--no-pdf-header-footer", "--print-to-pdf-no-header", f"--print-to-pdf={OUT}", "--virtual-time-budget=20000", temp.as_uri())
    if not OUT.exists():
        sys.exit("The browser did not write the PDF:\n" + done.stderr[-600:])
    print(f"wrote {OUT} ({OUT.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
