import pymupdf

from slides_diff.cli import diff, main


def test_output_pdf(beamer_pair, tmp_path):
    out = str(tmp_path / "diff.pdf")
    entries, old, new, pages = diff(*beamer_pair, out)
    doc = pymupdf.open(out)
    assert len(doc) == pages == 1 + len(entries)
    summary = doc[0].get_text()
    for word in ("unchanged", "new slide", "deleted", "moved", "changed: text", "changed: graphics"):
        assert word in summary
    # Page numbers in the footer shift after an insertion but are ignored.
    statuses = {new[e.op.new].title: e.status for e in entries if e.op.new is not None}
    assert statuses["Exercises"] == "unchanged"
    assert statuses["Summary of results"] == "moved"
    assert len(doc.get_toc()) == 1 + len(entries)
    assert len(doc[0].get_links()) == len(entries)


def test_changed_only(beamer_pair, tmp_path):
    out = str(tmp_path / "diff.pdf")
    entries, _, _, pages = diff(*beamer_pair, out, changed_only=True)
    unchanged = sum(e.status == "unchanged" for e in entries)
    assert pages == 1 + len(entries) - unchanged


def test_cli(beamer_pair, tmp_path, capsys):
    out = str(tmp_path / "cli.pdf")
    main([*beamer_pair, "-o", out, "--report", "--no-visual"])
    assert "Further reading" in capsys.readouterr().out
    assert pymupdf.open(out).page_count > 1
