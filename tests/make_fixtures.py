"""Build test decks: two versions of a Beamer lecture with known edits.

Edits from v1 to v2:
- new slide "Motivation" inserted after the title (shifts every later slide)
- "Old approach" deleted
- text changed in "Definitions" and "Algorithm"
- figure changed in "Architecture"
- "Summary of results" moved before "Open problems"
- a \\pause added to "Examples" (2 overlays instead of 1)
- new slide "Further reading" added at the end

Run: python tests/make_fixtures.py [OUTDIR]   (needs latexmk + pdflatex)
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys

PREAMBLE = r"""\documentclass{beamer}
\usetheme{Madrid}
\usepackage{tikz}
\title{Distributed Systems}
\subtitle{Lecture 3}
\author{A. Teacher}
\date{2026}
\begin{document}
\frame{\titlepage}
"""


def frame(title: str, body: str) -> str:
    return f"\\begin{{frame}}{{{title}}}\n{body}\n\\end{{frame}}\n"


def items(*xs: str) -> str:
    return "\\begin{itemize}\n" + "\n".join(f"\\item {x}" for x in xs) + "\n\\end{itemize}"


def figure(color: str, shape: str) -> str:
    return (f"\\begin{{center}}\\begin{{tikzpicture}}\n"
            f"\\draw[fill={color}!40] (0,0) {shape};\n"
            f"\\draw[->, thick] (3,1) -- (5,1);\n\\draw (6,1) circle (0.8);\n"
            f"\\end{{tikzpicture}}\\end{{center}}")


def deck(version: int) -> str:
    v2 = version == 2
    f = []
    if v2:
        f.append(frame("Motivation", items("Why do we need distributed systems?", "Scalability and fault tolerance",
                                           "Geographic distribution of users")))
    f.append(frame("Definitions", items(
        "A distributed system is a collection of independent computers",
        "that appears to its users as a single coherent system" if not v2
        else "that appears to its users as one coherent system",
        "Nodes communicate only by exchanging messages",
    ) + ("\n\\vspace{1em}Note: clocks are not synchronized." if v2 else "")))
    if not v2:
        f.append(frame("Old approach", items("Mainframes with dumb terminals", "Centralized storage",
                                             "Single point of failure")))
    f.append(frame("Architecture", "Client and server:\n" + figure("red" if v2 else "blue",
                                                                  "rectangle (2,2)" if not v2 else "circle (1)")))
    f.append(frame("Examples", items("Web services and content delivery networks", "Peer-to-peer file sharing")
                   .replace("\\item Peer", "\\pause\n\\item Peer" if v2 else "\\item Peer")))
    f.append(frame("Algorithm", items(
        "Each process keeps a logical clock $L$",
        "On send: $L \\gets L + 1$, attach $L$ to the message",
        "On receive: $L \\gets \\max(L, L_m) + 1$" if not v2 else "On receive: $L \\gets \\max(L, L_m) + 2$",
    )))
    summary = frame("Summary of results", items("Lamport clocks give a partial order", "Vector clocks capture causality",
                                                 "Physical clocks need synchronization protocols"))
    problems = frame("Open problems", items("Byzantine faults in open systems", "Consensus at planetary scale"))
    f += [summary, problems] if v2 else [problems, summary]
    f.append(frame("Exercises", items("Prove that Lamport clocks respect causality",
                                      "Show a counterexample for the converse")))
    if v2:
        f.append(frame("Further reading", items("Tanenbaum and van Steen, Distributed Systems",
                                                "Lamport, Time, Clocks, and the Ordering of Events")))
    return PREAMBLE + "".join(f) + "\\end{document}\n"


def build(outdir: str) -> tuple[str, str]:
    os.makedirs(outdir, exist_ok=True)
    paths = []
    for v in (1, 2):
        name = f"lecture_v{v}"
        with open(os.path.join(outdir, name + ".tex"), "w") as fh:
            fh.write(deck(v))
        subprocess.run(["latexmk", "-pdf", "-interaction=nonstopmode", "-quiet", name + ".tex"],
                       cwd=outdir, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        paths.append(os.path.join(outdir, name + ".pdf"))
    return paths[0], paths[1]


def have_latex() -> bool:
    return shutil.which("latexmk") is not None and shutil.which("pdflatex") is not None


if __name__ == "__main__":
    print(*build(sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), "fixtures")))
