"""Command line interface."""

from __future__ import annotations

import argparse
import os
import sys

from .align import align
from .extract import load_slides
from .highlight import compare
from .render import make_entries, render
from .similarity import similarity_matrix


def diff(old_path: str, new_path: str, out_path: str, *, frames: bool = True, threshold: float = 0.35,
         visual: bool = True, changed_only: bool = False):
    """Run the whole pipeline. Returns (entries, old slides, new slides, output page count)."""
    doc_a, old = load_slides(old_path, frames=frames)
    doc_b, new = load_slides(new_path, frames=frames)
    if not old or not new:
        raise SystemExit("error: one of the PDFs has no pages")
    ops = align(similarity_matrix(old, new), threshold=threshold)
    changes = {
        k: compare(old[op.old], new[op.new], doc_a, doc_b, visual=visual)
        for k, op in enumerate(ops)
        if op.old is not None and op.new is not None
    }
    entries = make_entries(ops, old, new, changes)
    pages = render(out_path, doc_a, old, doc_b, new, entries, (old_path, new_path), changed_only=changed_only)
    return entries, old, new, pages


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(
        prog="slides-diff",
        description="Compare two PDF slide decks. Slides are aligned first, so added, deleted and moved "
        "slides are detected; matched slides are shown side by side with changes highlighted.",
    )
    p.add_argument("old", help="old version of the slides (PDF)")
    p.add_argument("new", help="new version of the slides (PDF)")
    p.add_argument("-o", "--output", help="output PDF (default: NEW.diff.pdf)")
    p.add_argument("--pages", action="store_true",
                   help="compare every page, instead of grouping Beamer overlays into frames")
    p.add_argument("--changed-only", action="store_true",
                   help="leave unchanged slides out of the output (they are still listed in the summary)")
    p.add_argument("--threshold", type=float, default=0.35,
                   help="minimum similarity (0-1) for two slides to be matched (default: 0.35)")
    p.add_argument("--no-visual", action="store_true", help="skip the pixel diff (text changes only)")
    p.add_argument("--report", action="store_true", help="print the alignment table")
    args = p.parse_args(argv)

    for path in (args.old, args.new):
        if not os.path.isfile(path):
            p.error(f"no such file: {path}")
    out = args.output or os.path.splitext(args.new)[0] + ".diff.pdf"
    entries, old, new, pages = diff(args.old, args.new, out, frames=not args.pages, threshold=args.threshold,
                                    visual=not args.no_visual, changed_only=args.changed_only)
    if args.report:
        for e in entries:
            a = "" if e.op.old is None else old[e.op.old].number
            b = "" if e.op.new is None else new[e.op.new].number
            print(f"{a!s:>4} {b!s:>4}  {e.status:<28} {e.title}")
    counts: dict[str, int] = {}
    for e in entries:
        key = e.status.split(":")[0].split(",")[0]
        counts[key] = counts.get(key, 0) + 1
    summary = ", ".join(f"{v} {k}" for k, v in counts.items())
    print(f"{len(old)} -> {len(new)} slides ({summary}). Wrote {out} ({pages} pages).", file=sys.stderr)


if __name__ == "__main__":
    main()
