"""Similarity between two slides, in [0, 1]."""

from __future__ import annotations

from difflib import SequenceMatcher

import numpy as np

from .extract import Slide

RICH_TEXT = 8  # slides with at least this many words are compared mostly by text


def text_similarity(a: list[str], b: list[str]) -> float:
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    sm = SequenceMatcher(None, a, b, autojunk=False)
    # quick_ratio() is a cheap upper bound: skip the full diff for clear misses.
    upper = sm.quick_ratio()
    if upper < 0.25:
        return upper
    return sm.ratio()


def visual_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """1 for identical thumbnails, ~0 when the content does not overlap.

    The difference is normalised by the amount of "ink" (pixels that differ
    from the background) so that two mostly-white slides are not similar
    just because they are both white.
    """
    ink = np.abs(a - np.median(a)).sum() + np.abs(b - np.median(b)).sum()
    if ink < 1e-6:
        return 1.0
    return float(np.clip(1.0 - np.abs(a - b).sum() / ink, 0.0, 1.0))


def slide_similarity(a: Slide, b: Slide) -> float:
    ta, tb = a.tokens, b.tokens
    vis = visual_similarity(a.thumb, b.thumb)
    if not ta and not tb:
        return vis
    txt = text_similarity(ta, tb)
    w_text = 0.8 if min(len(ta), len(tb)) >= RICH_TEXT else 0.5
    sim = w_text * txt + (1 - w_text) * vis
    if a.title and a.title == b.title:
        sim += 0.1
    return min(sim, 1.0)


def similarity_matrix(old: list[Slide], new: list[Slide]) -> np.ndarray:
    m = np.zeros((len(old), len(new)))
    for i, a in enumerate(old):
        for j, b in enumerate(new):
            m[i, j] = slide_similarity(a, b)
    return m
