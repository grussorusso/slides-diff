"""Align two slide sequences, allowing added, deleted and moved slides."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

MATCH, ADDED, DELETED, MOVED = "match", "added", "deleted", "moved"


@dataclass
class Op:
    kind: str
    old: int | None = None  # slide index in the old deck
    new: int | None = None  # slide index in the new deck
    sim: float | None = None


def align(sim: np.ndarray, threshold: float = 0.35, move_threshold: float = 0.8) -> list[Op]:
    """Global alignment (Needleman-Wunsch) on a similarity matrix.

    Matching old slide i with new slide j scores sim[i, j] - threshold, and
    skipping a slide (insert/delete) scores 0. So a pair is only matched when
    it is similar enough, and the best overall alignment keeps the slide order.
    Slides that were reordered cannot be matched that way: afterwards, a
    deleted and an added slide that are very similar are paired as "moved".
    """
    n, m = sim.shape
    score = np.zeros((n + 1, m + 1))
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            score[i, j] = max(
                score[i - 1, j - 1] + sim[i - 1, j - 1] - threshold,
                score[i - 1, j],
                score[i, j - 1],
            )

    ops: list[Op] = []
    i, j = n, m
    while i > 0 or j > 0:
        if i > 0 and j > 0 and sim[i - 1, j - 1] > threshold and np.isclose(
            score[i, j], score[i - 1, j - 1] + sim[i - 1, j - 1] - threshold
        ):
            ops.append(Op(MATCH, i - 1, j - 1, float(sim[i - 1, j - 1])))
            i, j = i - 1, j - 1
        elif i > 0 and np.isclose(score[i, j], score[i - 1, j]):
            ops.append(Op(DELETED, old=i - 1))
            i -= 1
        else:
            ops.append(Op(ADDED, new=j - 1))
            j -= 1
    ops.reverse()
    _pair_moves(ops, sim, move_threshold)
    return ops


def _pair_moves(ops: list[Op], sim: np.ndarray, move_threshold: float) -> None:
    deleted = [op.old for op in ops if op.kind == DELETED]
    added = [op.new for op in ops if op.kind == ADDED]
    pairs = sorted(
        ((sim[a, b], a, b) for a in deleted for b in added if sim[a, b] >= move_threshold),
        reverse=True,
    )
    moved: dict[int, tuple[int, float]] = {}  # new index -> (old index, sim)
    used_old: set[int] = set()
    for s, a, b in pairs:
        if a not in used_old and b not in moved:
            moved[b] = (a, float(s))
            used_old.add(a)
    if not moved:
        return
    result = []
    for op in ops:
        if op.kind == DELETED and op.old in used_old:
            continue  # shown at the slide's new position instead
        if op.kind == ADDED and op.new in moved:
            a, s = moved[op.new]
            op = Op(MOVED, a, op.new, s)
        result.append(op)
    ops[:] = result
