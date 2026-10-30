"""Find what changed between two matched slides."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from difflib import SequenceMatcher

import numpy as np
import pymupdf

from .extract import Slide, Word

DIFF_WIDTH = 480  # pixel width used for the visual diff
PIXEL_THRESHOLD = 40  # 0-255 colour difference that counts as a change
CELL = 6  # pixel diff is grouped into CELL x CELL cells
EXPLAINED = 0.85  # drop visual regions mostly covered by text changes
MOVE_TOLERANCE = 1.5  # points; words shifted more than this count as moved


@dataclass
class Changes:
    old_words: list[pymupdf.Rect] = field(default_factory=list)  # deleted text
    new_words: list[pymupdf.Rect] = field(default_factory=list)  # inserted text
    old_regions: list[pymupdf.Rect] = field(default_factory=list)  # visual changes
    new_regions: list[pymupdf.Rect] = field(default_factory=list)
    layout_moved: bool = False  # same words, different positions
    overlays: tuple[int, int] = (1, 1)

    @property
    def changed(self) -> bool:
        return bool(
            self.old_words
            or self.new_words
            or self.old_regions
            or self.new_regions
            or self.layout_moved
            or self.overlays[0] != self.overlays[1]
        )

    def describe(self) -> str:
        parts = []
        if self.old_words or self.new_words:
            parts.append("text")
        if self.old_regions or self.new_regions:
            parts.append("graphics")
        if self.layout_moved and not parts:
            parts.append("layout")
        if self.overlays[0] != self.overlays[1]:
            parts.append(f"overlays {self.overlays[0]}->{self.overlays[1]}")
        return ", ".join(parts)


def _merge_boxes(words: list[Word], indices: range) -> list[pymupdf.Rect]:
    """Union consecutive words on the same line into one box."""
    boxes: list[pymupdf.Rect] = []
    prev_line = None
    for k in indices:
        w = words[k]
        if boxes and w.line == prev_line:
            boxes[-1] = boxes[-1] | w.rect
        else:
            boxes.append(pymupdf.Rect(w.rect))
        prev_line = w.line
    return boxes


def word_changes(a: Slide, b: Slide, changes: Changes) -> tuple[list[pymupdf.Rect], list[pymupdf.Rect]]:
    """Fill in changed-word boxes. Returns boxes of words that moved, for both pages."""
    sm = SequenceMatcher(None, a.tokens, b.tokens, autojunk=False)
    moved_a, moved_b = [], []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag in ("replace", "delete"):
            changes.old_words += _merge_boxes(a.words, range(i1, i2))
        if tag in ("replace", "insert"):
            changes.new_words += _merge_boxes(b.words, range(j1, j2))
        if tag == "equal":
            for i, j in zip(range(i1, i2), range(j1, j2)):
                ra, rb = a.words[i].rect, b.words[j].rect
                if abs(ra.x0 - rb.x0) > MOVE_TOLERANCE or abs(ra.y0 - rb.y0) > MOVE_TOLERANCE:
                    moved_a.append(ra)
                    moved_b.append(rb)
    changes.layout_moved = bool(moved_a)
    return moved_a, moved_b


def _render(page: pymupdf.Page, width: int, height: int) -> np.ndarray:
    m = pymupdf.Matrix(width / page.rect.width, height / page.rect.height)
    pix = page.get_pixmap(matrix=m, colorspace=pymupdf.csRGB, alpha=False)
    img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.stride)
    img = img[:, : pix.width * 3].reshape(pix.height, pix.width, 3)
    out = np.full((height, width, 3), 255, dtype=np.uint8)  # guard against rounding
    h, w = min(height, img.shape[0]), min(width, img.shape[1])
    out[:h, :w] = img[:h, :w]
    return out


def _box_mask(shape: tuple[int, int], boxes, sx: float, sy: float, pad: int = 2) -> np.ndarray:
    mask = np.zeros(shape, dtype=bool)
    for r in boxes:
        x0, y0 = max(int(r.x0 * sx) - pad, 0), max(int(r.y0 * sy) - pad, 0)
        x1, y1 = int(r.x1 * sx) + pad + 1, int(r.y1 * sy) + pad + 1
        mask[y0:y1, x0:x1] = True
    return mask


def _regions(cells: np.ndarray) -> list[tuple[int, int, int, int]]:
    """Bounding boxes (r0, c0, r1, c1) of 8-connected groups of True cells."""
    seen = np.zeros_like(cells)
    boxes = []
    rows, cols = cells.shape
    for r, c in zip(*np.nonzero(cells)):
        if seen[r, c]:
            continue
        seen[r, c] = True
        queue = deque([(r, c)])
        r0, c0, r1, c1 = r, c, r, c
        while queue:
            y, x = queue.popleft()
            r0, c0, r1, c1 = min(r0, y), min(c0, x), max(r1, y), max(c1, x)
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    ny, nx = y + dy, x + dx
                    if 0 <= ny < rows and 0 <= nx < cols and cells[ny, nx] and not seen[ny, nx]:
                        seen[ny, nx] = True
                        queue.append((ny, nx))
        boxes.append((r0, c0, r1 + 1, c1 + 1))
    return boxes


def visual_changes(pa: pymupdf.Page, pb: pymupdf.Page, explained_a, explained_b, changes: Changes) -> None:
    """Outline areas whose pixels changed and that the text diff does not explain."""
    ra, rb = pa.rect, pb.rect
    if abs(ra.width / ra.height - rb.width / rb.height) > 0.02:
        return  # different aspect ratio: pixels cannot be compared
    width = DIFF_WIDTH
    height = round(width * ra.height / ra.width)
    diff = np.abs(_render(pa, width, height).astype(int) - _render(pb, width, height)).max(axis=2)
    mask = diff > PIXEL_THRESHOLD
    if not mask.any():
        return
    sxa, sya = width / ra.width, height / ra.height
    sxb, syb = width / rb.width, height / rb.height
    explained = _box_mask(mask.shape, explained_a, sxa, sya) | _box_mask(mask.shape, explained_b, sxb, syb)

    # Group changed pixels into cells, then cells into regions.
    rows, cols = -(-height // CELL), -(-width // CELL)
    padded = np.zeros((rows * CELL, cols * CELL), dtype=bool)
    padded[:height, :width] = mask
    cells = padded.reshape(rows, CELL, cols, CELL).any(axis=(1, 3))
    # Dilate by one cell so nearby changes form a single region.
    grown = cells.copy()
    grown[1:] |= cells[:-1]
    grown[:-1] |= cells[1:]
    grown[:, 1:] |= grown[:, :-1].copy()
    grown[:, :-1] |= grown[:, 1:].copy()

    for r0, c0, r1, c1 in _regions(grown):
        y0, x0, y1, x1 = r0 * CELL, c0 * CELL, min(r1 * CELL, height), min(c1 * CELL, width)
        changed = mask[y0:y1, x0:x1]
        n = changed.sum()
        if n == 0 or (changed & explained[y0:y1, x0:x1]).sum() >= EXPLAINED * n:
            continue
        changes.old_regions.append(pymupdf.Rect(x0 / sxa, y0 / sya, x1 / sxa, y1 / sya))
        changes.new_regions.append(pymupdf.Rect(x0 / sxb, y0 / syb, x1 / sxb, y1 / syb))


def compare(a: Slide, b: Slide, doc_a: pymupdf.Document, doc_b: pymupdf.Document, visual: bool = True) -> Changes:
    changes = Changes(overlays=(len(a.pages), len(b.pages)))
    moved_a, moved_b = word_changes(a, b, changes)
    if visual:
        explained_a = changes.old_words + moved_a + a.ignored
        explained_b = changes.new_words + moved_b + b.ignored
        visual_changes(doc_a[a.rep_page], doc_b[b.rep_page], explained_a, explained_b, changes)
    return changes
