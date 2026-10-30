"""Build the output PDF: summary table plus one side-by-side page per slide."""

from __future__ import annotations

import os
from dataclasses import dataclass

import pymupdf

from .align import ADDED, DELETED, MATCH, MOVED, Op
from .extract import Slide
from .highlight import Changes

MARGIN = 12
HEADER = 26
FONT = "helv"

GRAY = (0.45, 0.45, 0.45)
RED = (0.82, 0.12, 0.12)
GREEN = (0.10, 0.55, 0.15)
ORANGE = (0.95, 0.55, 0.0)
BLUE = (0.10, 0.35, 0.80)
PURPLE = (0.50, 0.20, 0.70)
BLACK = (0, 0, 0)


@dataclass
class Entry:
    op: Op
    changes: Changes | None
    status: str
    color: tuple[float, float, float]
    title: str
    page: int | None = None  # output page index, if the entry gets a page
    summary_page: int = 0


def _latin1(text: str) -> str:
    """The built-in Helvetica font only covers Latin-1."""
    return text.encode("latin-1", "replace").decode("latin-1")


def _fit_text(text: str, size: float, width: float) -> str:
    text = _latin1(text)
    if pymupdf.get_text_length(text, FONT, size) <= width:
        return text
    while text and pymupdf.get_text_length(text + "...", FONT, size) > width:
        text = text[:-1]
    return text + "..."


def _fit(src: pymupdf.Rect, box: pymupdf.Rect) -> tuple[pymupdf.Rect, float]:
    """Largest rect with src's aspect ratio, centred in box, and its scale."""
    s = min(box.width / src.width, box.height / src.height)
    w, h = src.width * s, src.height * s
    x0 = box.x0 + (box.width - w) / 2
    y0 = box.y0 + (box.height - h) / 2
    return pymupdf.Rect(x0, y0, x0 + w, y0 + h), s


def _map(r: pymupdf.Rect, target: pymupdf.Rect, s: float) -> pymupdf.Rect:
    return pymupdf.Rect(target.x0 + r.x0 * s, target.y0 + r.y0 * s, target.x0 + r.x1 * s, target.y0 + r.y1 * s)


def make_entries(ops: list[Op], old: list[Slide], new: list[Slide], changes: dict[int, Changes]) -> list[Entry]:
    entries = []
    for k, op in enumerate(ops):
        ch = changes.get(k)
        if op.kind == MATCH:
            if ch.changed:
                status, color = f"changed: {ch.describe()}", ORANGE
            else:
                status, color = "unchanged", GRAY
            title = new[op.new].title or old[op.old].title
        elif op.kind == MOVED:
            extra = f", changed: {ch.describe()}" if ch.changed else ""
            status, color = f"moved{extra}", PURPLE
            title = new[op.new].title or old[op.old].title
        elif op.kind == ADDED:
            status, color, title = "new slide", GREEN, new[op.new].title
        else:
            status, color, title = "deleted", RED, old[op.old].title
        entries.append(Entry(op, ch, status, color, title))
    return entries


class Renderer:
    def __init__(self, doc_a, old: list[Slide], doc_b, new: list[Slide], names: tuple[str, str]):
        self.doc_a, self.doc_b = doc_a, doc_b
        self.old, self.new = old, new
        self.names = names
        rects = [doc_a[s.rep_page].rect for s in old] + [doc_b[s.rep_page].rect for s in new]
        self.slide_w = max(r.width for r in rects)
        self.slide_h = max(r.height for r in rects)
        self.width = 2 * self.slide_w + 3 * MARGIN
        self.height = self.slide_h + HEADER + 2 * MARGIN
        # Text sizes scale with the slide size (Beamer slides are small).
        self.fs = max(7.0, self.slide_h / 32)
        self.out = pymupdf.open()
        # Summary links point to later pages: added once those pages exist.
        self.pending_links: list[tuple[int, pymupdf.Rect, int]] = []

    # -- summary ---------------------------------------------------------

    def _rows_per_page(self, first: bool) -> int:
        top = MARGIN + (4.2 if first else 1.2) * self.fs * 1.6
        return max(1, int((self.height - top - MARGIN) / (self.fs * 1.35)))

    def summary_pages_needed(self, n_rows: int) -> int:
        first = self._rows_per_page(True)
        if n_rows <= first:
            return 1
        return 1 + -(-(n_rows - first) // self._rows_per_page(False))

    def render_summary(self, entries: list[Entry]) -> None:
        fs = self.fs
        row_h = fs * 1.35
        counts = {}
        for e in entries:
            key = e.status.split(":")[0].split(",")[0]
            counts[key] = counts.get(key, 0) + 1
        cols = [MARGIN, MARGIN + 3 * fs, MARGIN + 6.5 * fs, MARGIN + 10 * fs, MARGIN + 25 * fs]
        title_w = self.width - cols[4] - MARGIN

        k = 0
        first = True
        while k < len(entries) or first:
            page = self.out.new_page(width=self.width, height=self.height)
            y = MARGIN + fs * 1.4
            if first:
                a, b = (os.path.basename(n) for n in self.names)
                page.insert_text((MARGIN, y), _fit_text(f"slides-diff: {a} -> {b}", fs * 1.4, self.width - 2 * MARGIN),
                                 fontsize=fs * 1.4, fontname=FONT)
                y += fs * 1.8
                order = ["unchanged", "changed", "moved", "new slide", "deleted"]
                summary = "   ".join(f"{name}: {counts[name]}" for name in order if name in counts)
                page.insert_text((MARGIN, y), _latin1(f"{len(self.old)} -> {len(self.new)} slides.   {summary}"),
                                 fontsize=fs, fontname=FONT, color=GRAY)
                y += fs * 2.0
            for x, head in zip(cols, ["#", "Old", "New", "Status", "Title"]):
                page.insert_text((x, y), head, fontsize=fs, fontname="hebo")
            y += fs * 0.5
            page.draw_line((MARGIN, y), (self.width - MARGIN, y), color=GRAY, width=0.5)
            y += row_h
            for _ in range(self._rows_per_page(first)):
                if k >= len(entries):
                    break
                e = entries[k]
                e.summary_page = page.number
                old = "" if e.op.old is None else str(self.old[e.op.old].number)
                new = "" if e.op.new is None else str(self.new[e.op.new].number)
                values = [str(k + 1), old, new]
                for x, v in zip(cols, values):
                    page.insert_text((x, y), v, fontsize=fs, fontname=FONT)
                page.insert_text((cols[3], y), _fit_text(e.status, fs, cols[4] - cols[3] - fs), fontsize=fs,
                                 fontname=FONT, color=e.color)
                page.insert_text((cols[4], y), _fit_text(e.title, fs, title_w), fontsize=fs, fontname=FONT)
                if e.page is not None:
                    link = pymupdf.Rect(MARGIN, y - fs, self.width - MARGIN, y + fs * 0.3)
                    self.pending_links.append((page.number, link, e.page))
                y += row_h
                k += 1
            first = False

    # -- slide pages -----------------------------------------------------

    def _halves(self) -> tuple[pymupdf.Rect, pymupdf.Rect]:
        top = HEADER + MARGIN
        left = pymupdf.Rect(MARGIN, top, MARGIN + self.slide_w, top + self.slide_h)
        right = pymupdf.Rect(2 * MARGIN + self.slide_w, top, 2 * MARGIN + 2 * self.slide_w, top + self.slide_h)
        return left, right

    def _place(self, page, box, doc, slide: Slide, frame_color) -> tuple[pymupdf.Rect, float]:
        src = doc[slide.rep_page]
        target, s = _fit(src.rect, box)
        page.show_pdf_page(target, doc, slide.rep_page)
        page.draw_rect(target, color=frame_color, width=1.0)
        return target, s

    def _placeholder(self, page, box, text, color) -> None:
        page.draw_rect(box, color=color, width=1.0, dashes="[4 4] 0")
        size = self.fs * 2.5
        y = box.y0 + box.height / 2 + size / 3
        x = box.x0 + (box.width - pymupdf.get_text_length(text, "hebo", size)) / 2
        page.insert_text((x, y), text, fontsize=size, fontname="hebo", color=color)

    def _highlight(self, page, rects, target, s, fill) -> None:
        for r in rects:
            page.draw_rect(_map(r, target, s), color=None, fill=fill, width=0, fill_opacity=0.3)

    def _outline(self, page, rects, target, s) -> None:
        for r in rects:
            page.draw_rect(_map(r, target, s) + (-1, -1, 1, 1), color=ORANGE, width=1.2)

    def _header(self, page, e: Entry) -> None:
        fs = self.fs
        y = MARGIN + fs
        parts = []
        if e.op.old is not None:
            parts.append(f"old {self.old[e.op.old].number}")
        if e.op.new is not None:
            parts.append(f"new {self.new[e.op.new].number}")
        left = " | ".join(parts)
        if e.op.sim is not None:
            left += f"   (similarity {e.op.sim:.2f})"
        page.insert_text((MARGIN, y), left, fontsize=fs * 1.1, fontname="hebo")
        status_x = MARGIN + pymupdf.get_text_length(left, "hebo", fs * 1.1) + 2 * fs
        page.insert_text((status_x, y), _latin1(e.status), fontsize=fs * 1.1, fontname="hebo", color=e.color)
        back = "summary"
        bx = self.width - MARGIN - pymupdf.get_text_length(back, FONT, fs)
        page.insert_text((bx, y), back, fontsize=fs, fontname=FONT, color=BLUE)
        page.insert_link({"kind": pymupdf.LINK_GOTO, "from": pymupdf.Rect(bx, y - fs, self.width - MARGIN, y + 2),
                          "page": e.summary_page})
        title_w = bx - MARGIN - fs
        page.insert_text((MARGIN, y + fs * 1.4), _fit_text(e.title, fs, title_w), fontsize=fs, fontname=FONT,
                         color=GRAY)
        page.draw_rect(pymupdf.Rect(0, 0, 4, self.height), color=None, fill=e.color, width=0)

    def render_entry(self, e: Entry) -> None:
        page = self.out.new_page(width=self.width, height=self.height)
        self._header(page, e)
        left, right = self._halves()
        op, ch = e.op, e.changes
        if op.kind in (MATCH, MOVED):
            ta, sa = self._place(page, left, self.doc_a, self.old[op.old], GRAY)
            tb, sb = self._place(page, right, self.doc_b, self.new[op.new], GRAY)
            self._highlight(page, ch.old_words, ta, sa, RED)
            self._highlight(page, ch.new_words, tb, sb, GREEN)
            self._outline(page, ch.old_regions, ta, sa)
            self._outline(page, ch.new_regions, tb, sb)
        elif op.kind == ADDED:
            self._placeholder(page, left, "NEW SLIDE", GREEN)
            self._place(page, right, self.doc_b, self.new[op.new], GREEN)
        elif op.kind == DELETED:
            self._place(page, left, self.doc_a, self.old[op.old], RED)
            self._placeholder(page, right, "DELETED", RED)

    def toc(self, entries: list[Entry]) -> list[list]:
        toc = [[1, "Summary", 1]]
        for e in entries:
            if e.page is None:
                continue
            nums = []
            if e.op.old is not None:
                nums.append(f"old {self.old[e.op.old].number}")
            if e.op.new is not None:
                nums.append(f"new {self.new[e.op.new].number}")
            label = f"{' | '.join(nums)} [{e.status}]"
            if e.title:
                label += f" {e.title}"
            toc.append([1, label, e.page + 1])
        return toc


def render(out_path: str, doc_a, old, doc_b, new, entries: list[Entry], names: tuple[str, str],
           changed_only: bool = False) -> int:
    r = Renderer(doc_a, old, doc_b, new, names)
    n_summary = r.summary_pages_needed(len(entries))
    next_page = n_summary
    for e in entries:
        if changed_only and e.status == "unchanged":
            continue
        e.page = next_page
        next_page += 1
    r.render_summary(entries)
    for e in entries:
        if e.page is not None:
            r.render_entry(e)
    for pno, rect, target in r.pending_links:
        r.out[pno].insert_link({"kind": pymupdf.LINK_GOTO, "from": rect, "page": target})
    r.out.set_toc(r.toc(entries))
    r.out.save(out_path, garbage=3, deflate=True)
    return len(r.out)
