# slides-diff

Compare two versions of a slide deck (PDF) and get a PDF report with the
slides side by side.

Unlike page-by-page PDF diff tools, `slides-diff` first **aligns** the two
decks, so an added or deleted slide doesn't make every later page get
compared with the wrong one.

- **Matched slides** are shown side by side: changed words highlighted
  (red = removed, green = added), changed graphics outlined in orange.
- **New slides** and **deleted slides** are reported, not compared.
- **Moved slides** (reordered) are detected and compared.
- **Beamer overlays** are grouped into one frame (using the PDF page labels
  Beamer writes); the last overlay is compared and a change in the number of
  overlays is reported.
- Page/frame numbers in the footer are ignored, since they shift after any
  insertion.
- The first page is a summary table with links to each comparison; the PDF
  outline (bookmarks) lists every slide too.

## Install

```sh
python3 -m venv .venv
.venv/bin/pip install -e .
```

Requires Python 3.10+, PyMuPDF and numpy.

## Usage

```sh
slides-diff old.pdf new.pdf                # writes new.diff.pdf
slides-diff old.pdf new.pdf -o report.pdf --report
```

| Option | Meaning |
| --- | --- |
| `-o FILE` | output PDF (default `NEW.diff.pdf`) |
| `--changed-only` | leave unchanged slides out of the output (still in the summary) |
| `--pages` | compare every page; don't group overlays into frames |
| `--threshold F` | minimum similarity (0–1) to match two slides (default 0.35) |
| `--no-visual` | text diff only, skip the pixel diff |
| `--report` | print the alignment table on stdout |

To diff two commits of a Beamer source, compile both and compare the PDFs, e.g.:

```sh
git worktree add /tmp/old HEAD~3 && (cd /tmp/old && latexmk -pdf lecture.tex)
latexmk -pdf lecture.tex
slides-diff /tmp/old/lecture.pdf lecture.pdf
```

## How it works

1. **Extract** (`extract.py`): text, word boxes, title and a small thumbnail
   per slide; overlay pages are grouped into frames.
2. **Similarity** (`similarity.py`): a mix of word-sequence similarity,
   thumbnail similarity (weighted more for slides with little text) and a
   bonus for equal titles.
3. **Align** (`align.py`): Needleman–Wunsch global alignment. Matching costs
   `similarity - threshold`, skipping costs 0, so only similar slides are
   paired and order is preserved. Leftover deleted/added pairs with
   similarity ≥ 0.8 are reported as moved.
4. **Highlight** (`highlight.py`): word diff on the matched pair; pixel diff
   at ~480 px width, grouped into regions; regions explained by text changes
   are dropped.
5. **Render** (`render.py`): the original pages are embedded as vectors, so
   the report stays sharp and searchable.

## Tests

```sh
.venv/bin/pip install -e '.[test]'
.venv/bin/pytest
```

The Beamer tests build two small decks with known edits (needs `latexmk`);
`python tests/make_fixtures.py` writes them to `tests/fixtures/`.
