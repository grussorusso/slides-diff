"""Load a PDF deck into a list of slides (frames)."""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field

import numpy as np
import pymupdf

THUMB_SHAPE = (48, 64)  # rows, cols

# Tokens made only of digits and separators near the bottom of the page are
# treated as page/frame numbers: they change whenever a slide is added before
# them, so they are ignored when comparing.
_NUMBER_RE = re.compile(r"^[\d/.,:()\-–]+$")
FOOTER_FRACTION = 0.12


@dataclass
class Word:
    text: str
    rect: pymupdf.Rect
    line: tuple[int, int]  # (block, line), used to merge highlight boxes


@dataclass
class Slide:
    index: int  # 0-based slide index in the deck
    pages: list[int]  # 0-based page numbers (several for overlays)
    label: str
    title: str
    words: list[Word]  # words used for comparison (footer numbers removed)
    ignored: list[pymupdf.Rect]  # boxes of ignored footer numbers
    thumb: np.ndarray = field(repr=False)

    @property
    def rep_page(self) -> int:
        """The page used for comparison: the last (complete) overlay."""
        return self.pages[-1]

    @property
    def tokens(self) -> list[str]:
        return [w.text for w in self.words]

    @property
    def number(self) -> int:
        """1-based slide number for display."""
        return self.index + 1


def page_label(page: pymupdf.Page) -> str:
    """Page label, decoding the <FEFF...> hex form some PyMuPDF versions return."""
    label = page.get_label()
    m = re.fullmatch(r"<([0-9A-Fa-f]+)>", label)
    if m:
        try:
            raw = bytes.fromhex(m.group(1))
            label = raw[2:].decode("utf-16-be") if raw[:2] == b"\xfe\xff" else raw.decode("latin-1")
        except ValueError:
            pass
    return label


def _page_words(page: pymupdf.Page) -> tuple[list[Word], list[pymupdf.Rect]]:
    footer_y = page.rect.y1 - FOOTER_FRACTION * page.rect.height
    words, ignored = [], []
    for x0, y0, x1, y1, text, block, line, _ in page.get_text("words", sort=True):
        rect = pymupdf.Rect(x0, y0, x1, y1)
        if y0 >= footer_y and _NUMBER_RE.match(text):
            ignored.append(rect)
        else:
            words.append(Word(text, rect, (block, line)))
    return words, ignored


def _page_title(page: pymupdf.Page) -> str:
    """Guess the slide title: the line(s) with the biggest font in the top part."""
    top = page.rect.y0 + 0.3 * page.rect.height
    best_size, boxes = 0.0, []
    for block in page.get_text("dict")["blocks"]:
        for line in block.get("lines", []):
            spans = [s for s in line["spans"] if s["text"].strip()]
            if not spans or line["bbox"][1] > top:
                continue
            size = max(s["size"] for s in spans)
            if size > best_size + 0.5:
                best_size, boxes = size, [line["bbox"]]
            elif abs(size - best_size) <= 0.5:
                boxes.append(line["bbox"])
    # Span text can lack spaces (pdflatex does not emit them); get_textbox
    # restores them from glyph gaps.
    return " ".join(" ".join(page.get_textbox(b).split()) for b in boxes)


def _thumbnail(page: pymupdf.Page) -> np.ndarray:
    rows, cols = THUMB_SHAPE
    zoom = 2 * cols / page.rect.width
    pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), colorspace=pymupdf.csGRAY)
    img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.stride)
    img = img[:, : pix.width].astype(np.float32)
    # Resize to a fixed shape (nearest-neighbour sampling).
    ri = (np.arange(rows) * img.shape[0] / rows).astype(int)
    ci = (np.arange(cols) * img.shape[1] / cols).astype(int)
    return img[np.ix_(ri, ci)]


def _is_overlay_step(prev: list[Word], cur: list[Word]) -> bool:
    """True if `cur` looks like the next overlay of `prev` (same text plus more)."""
    a, b = Counter(w.text for w in prev), Counter(w.text for w in cur)
    if not a or sum(b.values()) <= sum(a.values()):
        return False
    return not (a - b)  # every word of prev is still there


def group_frames(doc: pymupdf.Document, words: list[list[Word]]) -> list[list[int]]:
    """Group consecutive overlay pages into frames.

    Beamer gives all pages of a frame the same page label. Without labels we
    fall back to a text heuristic: a page whose words are a subset of the
    next page's words is an earlier overlay of the same frame.
    """
    labels = [page_label(page) for page in doc]
    use_labels = any(labels) and len(set(labels)) < len(labels)
    groups: list[list[int]] = []
    for i in range(len(doc)):
        if groups:
            prev = groups[-1][-1]
            same = (labels[i] == labels[prev]) if use_labels else _is_overlay_step(words[prev], words[i])
            if same:
                groups[-1].append(i)
                continue
        groups.append([i])
    return groups


def load_slides(path: str, frames: bool = True) -> tuple[pymupdf.Document, list[Slide]]:
    doc = pymupdf.open(path)
    per_page = [_page_words(page) for page in doc]
    if frames:
        groups = group_frames(doc, [w for w, _ in per_page])
    else:
        groups = [[i] for i in range(len(doc))]
    slides = []
    for idx, pages in enumerate(groups):
        page = doc[pages[-1]]
        words, ignored = per_page[pages[-1]]
        slides.append(
            Slide(
                index=idx,
                pages=pages,
                label=page_label(page),
                title=_page_title(page),
                words=words,
                ignored=ignored,
                thumb=_thumbnail(page),
            )
        )
    return doc, slides
