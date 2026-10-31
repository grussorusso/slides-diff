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

Requires Python 3.10 or newer. PyMuPDF and numpy are installed automatically.

From the project folder, create a virtual environment and install the tool
into it:

```sh
cd slides-diff
python3 -m venv .venv
.venv/bin/pip install -e .
```

This creates the command `.venv/bin/slides-diff`. To run it as plain
`slides-diff` from any folder, choose one of these:

- link it into a folder on your `PATH` (for example `~/.local/bin`):
  ```sh
  ln -s "$PWD/.venv/bin/slides-diff" ~/.local/bin/slides-diff
  ```
- or activate the environment in the current shell:
  `source .venv/bin/activate`
- or install with [pipx](https://pipx.pypa.io) instead of the steps above:
  `pipx install -e .`

Because of `-e` (editable install), changes to the code take effect without
reinstalling.

## Usage

```sh
slides-diff OLD.pdf NEW.pdf [options]
```

Examples:

```sh
slides-diff old.pdf new.pdf                     # writes new.diff.pdf
slides-diff old.pdf new.pdf -o report.pdf       # choose the output file
slides-diff old.pdf new.pdf --changed-only      # skip unchanged slides
slides-diff old.pdf new.pdf --report            # also print the alignment
```

If `slides-diff` is not on your `PATH`, use `.venv/bin/slides-diff` instead.
`slides-diff -h` lists all options:

| Option | Meaning |
| --- | --- |
| `-o FILE` | output PDF (default `NEW.diff.pdf`) |
| `--changed-only` | leave unchanged slides out of the output (still in the summary) |
| `--pages` | compare every page; don't group overlays into frames |
| `--threshold F` | minimum similarity (0–1) to match two slides (default 0.35) |
| `--no-visual` | text diff only, skip the pixel diff |
| `--report` | print the alignment table on stdout |

### Comparing two commits of a Beamer source

Compile both versions and compare the PDFs. For example, to compare the
current version of `lecture.tex` with the one from 3 commits ago (run from the
folder that contains `lecture.tex`):

```sh
git worktree add /tmp/old-slides HEAD~3                          # check out the old commit
(cd /tmp/old-slides/"$(git rev-parse --show-prefix)" && latexmk -pdf lecture.tex)
latexmk -pdf lecture.tex
slides-diff /tmp/old-slides/"$(git rev-parse --show-prefix)"lecture.pdf lecture.pdf
git worktree remove --force /tmp/old-slides                      # clean up
```

Replace `HEAD~3` with any commit, branch or tag.

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
