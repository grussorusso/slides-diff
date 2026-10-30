import pytest

from make_fixtures import build, have_latex


@pytest.fixture(scope="session")
def beamer_pair(tmp_path_factory):
    if not have_latex():
        pytest.skip("latexmk/pdflatex not available")
    return build(str(tmp_path_factory.mktemp("beamer")))
