"""
Convert docs/report/report.md into docs/report/report.tex (LaTeX, in the style of the homework reports).

    python build_tex.py            # run from docs/report/ ; writes report.tex next to report.md

report.md stays the single source of truth. Edit the Markdown, run this script again, and compile
report.tex with pdflatex (Overleaf or MiKTeX). Standard library only; this script does not compile anything.

Only the Markdown features that report.md actually uses are handled:
  # title, ## section, ### subsection, paragraphs, "- " bullets, pipe tables, ``` code blocks,
  ![caption](path) images (the italic "*Figure N: ...*" line after an image is dropped, LaTeX numbers figures itself),
  **bold**, *italic*, `code`, [text](url), bare URLs, and <!-- comments --> (kept as LaTeX comments).
"""
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC = HERE / "report.md"
OUT = HERE / "report.tex"

PREAMBLE = r"""\documentclass[11pt,letterpaper]{article}
\usepackage[T1]{fontenc}
\usepackage[utf8]{inputenc}
\usepackage{lmodern}
\usepackage[margin=1in]{geometry}
\usepackage{graphicx}
\usepackage{float}
\usepackage{longtable}
\usepackage{array}
\usepackage{xcolor}
\usepackage{listings}
\usepackage[hidelinks]{hyperref}

\setlength{\parindent}{0pt}
\setlength{\parskip}{6pt}
\setlength{\emergencystretch}{3em}
\renewcommand{\arraystretch}{1.15}

\lstset{
  basicstyle=\ttfamily\footnotesize,
  breaklines=true,
  columns=fullflexible,
  frame=single,
  framerule=0.3pt,
  rulecolor=\color{black!40},
  xleftmargin=0pt,
  aboveskip=6pt,
  belowskip=6pt
}

% inline code: typewriter, with places where a long name may break
\newcommand{\code}[1]{\texttt{#1}}
% a screenshot that has not been captured yet (still counts as a figure number)
\newcommand{\pendingfigure}[2]{%
  \refstepcounter{figure}%
  \begin{center}
  \fbox{\parbox{0.9\linewidth}{\centering\textbf{\textcolor{red!70!black}{SCREENSHOT PENDING}}\\[2pt]
  \texttt{#1}\\[2pt] Figure \thefigure: #2}}
  \end{center}}

\begin{document}
"""

POSTAMBLE = "\n\\end{document}\n"

# characters that are special in LaTeX
LATEX_ESC = {
    "\\": r"\textbackslash{}", "&": r"\&", "%": r"\%", "$": r"\$", "#": r"\#",
    "_": r"\_", "{": r"\{", "}": r"\}", "~": r"\textasciitilde{}", "^": r"\textasciicircum{}",
}
# the few non-ASCII characters used in report.md
UNICODE = {"–": "--", "—": "---", "×": r"$\times$", "·": r"$\cdot$", "≥": r"$\geq$", "≤": r"$\leq$",
           "→": r"$\rightarrow$", "’": "'", "“": "``", "”": "''", "…": r"\ldots{}"}


def esc_text(t):
    """Escape plain text (not code)."""
    out = []
    for ch in t:
        out.append(LATEX_ESC.get(ch, UNICODE.get(ch, ch)))
    s = "".join(out)
    # straight double quotes -> LaTeX quotes
    s = re.sub(r'"([^"]*)"', r"``\1''", s)
    return s


def esc_code(t):
    """Escape text for \\code{...} and allow line breaks after _ / . : - and so on."""
    out = []
    for ch in t:
        if ch in LATEX_ESC:
            out.append(LATEX_ESC[ch])
        elif ch in UNICODE:
            out.append(UNICODE[ch])
        else:
            out.append(ch)
        if ch in "_/.:-,=[]":
            out.append(r"\allowbreak{}")
    return "".join(out)


def inline(text):
    """Markdown inline formatting -> LaTeX."""
    tokens = []

    def keep(latex):
        tokens.append(latex)
        return f"\x00{len(tokens) - 1}\x00"

    # `code`
    text = re.sub(r"`([^`]+)`", lambda m: keep(r"\code{" + esc_code(m.group(1)) + "}"), text)
    # [text](url)
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)",
                  lambda m: keep(r"\href{" + m.group(2) + "}{" + esc_text(m.group(1)) + "}"), text)
    # bare URLs
    text = re.sub(r"https?://[^\s)]+", lambda m: keep(r"\url{" + m.group(0) + "}"), text)
    # inline HTML comment (rendered as nothing)
    text = re.sub(r"<!--.*?-->", "", text)

    text = esc_text(text)
    text = re.sub(r"\*\*(.+?)\*\*", r"\\textbf{\1}", text)
    text = re.sub(r"(?<![\w*])\*([^*\s][^*]*?)\*(?![\w*])", r"\\textit{\1}", text)

    return re.sub(r"\x00(\d+)\x00", lambda m: tokens[int(m.group(1))], text)


def split_row(line):
    """Split a pipe-table row into cells, ignoring pipes inside `code`."""
    line = line.strip()
    if line.startswith("|"):
        line = line[1:]
    if line.endswith("|"):
        line = line[:-1]
    cells, cur, in_code = [], "", False
    for ch in line:
        if ch == "`":
            in_code = not in_code
        if ch == "|" and not in_code:
            cells.append(cur.strip())
            cur = ""
        else:
            cur += ch
    cells.append(cur.strip())
    return cells


def table(lines):
    rows = [split_row(l) for l in lines]
    header, align_row, body = rows[0], rows[1], rows[2:]
    n = len(header)
    aligns = []
    for c in align_row:
        c = c.strip()
        aligns.append(r"\raggedleft\arraybackslash" if c.endswith(":") and not c.startswith(":")
                      else r"\centering\arraybackslash" if c.startswith(":") and c.endswith(":")
                      else r"\raggedright\arraybackslash")
    # column width is proportional to the longest cell (clamped so no column gets too thin or too wide)
    weights = []
    for i in range(n):
        longest = max(len(r[i]) if i < len(r) else 0 for r in rows if r is not align_row)
        weights.append(min(max(longest, 6), 55))
    total = float(sum(weights))
    spec = ""
    for i in range(n):
        frac = weights[i] / total
        spec += r">{" + aligns[i] + r"}p{\dimexpr " + f"{frac:.3f}" + r"\linewidth-2\tabcolsep\relax}"
    out = [r"{\small", r"\begin{longtable}{" + spec + "}", r"\hline"]
    head = " & ".join(r"\textbf{" + inline(c) + "}" for c in header) + r" \\ \hline"
    out += [head, r"\endhead"]
    for r in body:
        r = r + [""] * (n - len(r))
        out.append(" & ".join(inline(c) for c in r[:n]) + r" \\ \hline")
    out += [r"\end{longtable}", "}"]
    return "\n".join(out)


def convert(md):
    lines = md.split("\n")
    out = []
    i = 0
    title, byline = None, None
    para = []
    fig_count_pending = 0  # not used for numbering; LaTeX counts figures itself

    def flush_para():
        nonlocal para
        if para:
            out.append(inline(" ".join(p.strip() for p in para)))
            out.append("")
            para = []

    while i < len(lines):
        line = lines[i]

        # code block
        if line.startswith("```"):
            flush_para()
            i += 1
            block = []
            while i < len(lines) and not lines[i].startswith("```"):
                block.append(lines[i])
                i += 1
            i += 1
            out.append(r"\begin{lstlisting}")
            out += block
            out.append(r"\end{lstlisting}")
            out.append("")
            continue

        # whole-line HTML comment: keep as a LaTeX comment; partner placeholders also get a visible note
        m = re.match(r"^<!--\s*(.*?)\s*-->\s*$", line)
        if m:
            flush_para()
            note = m.group(1)
            out.append("% " + note)
            if note.startswith("PARTNER"):
                out.append(r"\textit{[To be added by Parts B and C from real runs.]}")
                out.append("")
            elif note.startswith("UDAY"):
                out.append(r"\textit{[To be added.]}")
                out.append("")
            i += 1
            continue

        # headings
        m = re.match(r"^(#{1,3}) (.*)$", line)
        if m:
            flush_para()
            level, text = len(m.group(1)), m.group(2).strip()
            if level == 1:
                title = text
            elif level == 2:
                mm = re.match(r"^(\d+)\.\s+(.*)$", text)
                heading = f"Section {mm.group(1)} -- {inline(mm.group(2))}" if mm else inline(text)
                out.append(r"\section*{" + heading + "}")
            else:
                mm = re.match(r"^(\d+\.\d+)\s+(.*)$", text)
                heading = f"{mm.group(1)} -- {inline(mm.group(2))}" if mm else inline(text)
                out.append(r"\subsection*{" + heading + "}")
            out.append("")
            i += 1
            continue

        # byline: the first paragraph after the title
        if title is not None and byline is None and line.strip() and not line.startswith("#"):
            byline = inline(line.strip())
            i += 1
            continue

        # image + caption (the italic "*Figure N: ...*" line that follows is dropped)
        m = re.match(r"^!\[(.*)\]\((.*)\)\s*$", line)
        if m:
            flush_para()
            cap = re.sub(r"^Figure \d+:\s*", "", m.group(1))
            out.append(r"\begin{figure}[H]")
            out.append(r"\centering")
            out.append(r"\includegraphics[width=\linewidth,height=0.42\textheight,keepaspectratio]{" + m.group(2) + "}")
            out.append(r"\caption{" + inline(cap) + "}")
            out.append(r"\end{figure}")
            out.append("")
            i += 1
            while i < len(lines) and not lines[i].strip():
                i += 1
            if i < len(lines) and lines[i].startswith("*Figure"):
                i += 1
            continue

        # pending screenshot line
        m = re.match(r"^\*\*SCREENSHOT PENDING: (.+?)\*\* \(Figure \d+: (.*)\)\s*$", line)
        if m:
            flush_para()
            out.append(r"\pendingfigure{" + esc_code(m.group(1)) + "}{" + inline(m.group(2)) + "}")
            out.append("")
            i += 1
            continue

        # table
        if line.lstrip().startswith("|") and i + 1 < len(lines) and re.match(r"^\s*\|[\s:|-]+\|\s*$", lines[i + 1]):
            flush_para()
            block = []
            while i < len(lines) and lines[i].lstrip().startswith("|"):
                block.append(lines[i])
                i += 1
            out.append(table(block))
            out.append("")
            continue

        # bullet list (continuation lines are indented)
        if re.match(r"^- ", line):
            flush_para()
            out.append(r"\begin{itemize}")
            while i < len(lines) and re.match(r"^- ", lines[i]):
                item = [lines[i][2:].strip()]
                i += 1
                while i < len(lines) and lines[i].startswith("  ") and lines[i].strip():
                    item.append(lines[i].strip())
                    i += 1
                out.append(r"\item " + inline(" ".join(item)))
            out.append(r"\end{itemize}")
            out.append("")
            continue

        # blank line ends a paragraph
        if not line.strip():
            flush_para()
            i += 1
            continue

        para.append(line)
        i += 1
    flush_para()

    head = [r"\begin{center}",
            r"{\LARGE\bfseries " + inline(title or "Report") + r"}\\[6pt]",
            (r"{\large " + byline + "}") if byline else "",
            r"\end{center}", ""]
    return "\n".join(head + out)


def main():
    md = SRC.read_text(encoding="utf-8")
    tex = PREAMBLE + convert(md) + POSTAMBLE
    OUT.write_text(tex, encoding="utf-8")
    left = sorted({c for c in tex if ord(c) > 127})
    print(f"wrote {OUT} ({len(tex.splitlines())} lines); non-ASCII characters left: {left or 'none'}")
    if tex.count("{") != tex.count("}"):
        # braces in escaped text are written as \{ and \}, so compare unescaped counts only as a rough check
        opens = len(re.findall(r"(?<!\\)\{", tex))
        closes = len(re.findall(r"(?<!\\)\}", tex))
        print(f"brace check: {opens} opening vs {closes} closing (unescaped)")
        if opens != closes:
            sys.exit("unbalanced braces: look at the generated report.tex")


if __name__ == "__main__":
    main()
