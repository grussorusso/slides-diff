import numpy as np
import pymupdf

from slides_diff.align import ADDED, DELETED, MATCH, MOVED, align
from slides_diff.extract import load_slides
from slides_diff.similarity import similarity_matrix


def ops_table(old_path, new_path, **kw):
    _, old = load_slides(old_path, **kw)
    _, new = load_slides(new_path, **kw)
    ops = align(similarity_matrix(old, new))
    return [(op.kind, op.old, op.new) for op in ops], old, new


def test_align_matrix_insert_shifts():
    # New slide inserted at position 0: all others must still match their twin.
    sim = np.array([[0.1, 0.95, 0.1, 0.1], [0.1, 0.1, 0.95, 0.1], [0.1, 0.1, 0.1, 0.95]])
    assert [(o.kind, o.old, o.new) for o in align(sim)] == [
        (ADDED, None, 0), (MATCH, 0, 1), (MATCH, 1, 2), (MATCH, 2, 3)]


def test_align_matrix_move():
    sim = np.array([[0.95, 0.1, 0.1], [0.1, 0.1, 0.95], [0.1, 0.95, 0.1]])
    kinds = [(o.kind, o.old, o.new) for o in align(sim)]
    assert (MOVED, 2, 1) in kinds or (MOVED, 1, 2) in kinds
    assert not any(k in (ADDED, DELETED) for k, _, _ in kinds)


def test_beamer_alignment(beamer_pair):
    table, old, new = ops_table(*beamer_pair)
    assert table == [
        (MATCH, 0, 0),      # title
        (ADDED, None, 1),   # Motivation
        (MATCH, 1, 2),      # Definitions (text changed)
        (DELETED, 2, None), # Old approach
        (MATCH, 3, 3),      # Architecture (figure changed)
        (MATCH, 4, 4),      # Examples (overlay added)
        (MATCH, 5, 5),      # Algorithm (text changed)
        (MOVED, 7, 6),      # Summary of results
        (MATCH, 6, 7),      # Open problems
        (MATCH, 8, 8),      # Exercises
        (ADDED, None, 9),   # Further reading
    ]
    assert new[4].pages == [4, 5]  # overlay pages grouped into one frame
    assert new[4].title == "Examples"


def test_beamer_page_level(beamer_pair):
    table, _, new = ops_table(*beamer_pair, frames=False)
    assert len(new) == 11
    # The first overlay of "Examples" shows up as an added page.
    assert (ADDED, None, 4) in table


def _deck(path, pages):
    doc = pymupdf.open()
    for lines in pages:
        page = doc.new_page(width=400, height=300)
        for k, line in enumerate(lines):
            page.insert_text((30, 40 + 22 * k), line, fontsize=14 if k == 0 else 11)
    doc.save(path)


def test_overlay_fallback_without_labels(tmp_path):
    a, b = str(tmp_path / "a.pdf"), str(tmp_path / "b.pdf")
    base = [
        ["Intro", "what this course is about", "who teaches it"],
        ["Topic one", "first point here", "second point here"],
        ["Topic two", "another slide entirely", "with other words"],
    ]
    _deck(a, base)
    # v2: "Topic one" revealed in two steps, plus a new slide in front.
    _deck(b, [["Welcome", "a brand new opening slide", "nothing similar"], base[0],
              base[1][:2], base[1], base[2]])
    table, _, new = ops_table(a, b)
    assert new[2].pages == [2, 3]
    assert table == [(ADDED, None, 0), (MATCH, 0, 1), (MATCH, 1, 2), (MATCH, 2, 3)]
