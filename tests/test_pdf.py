import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from jobagent.documents import guard, pdf, tailor

ROOT = Path(__file__).resolve().parents[1]
MASTER = yaml.safe_load((ROOT / "master.example.yaml").read_text(encoding="utf-8"))


def _content():
    changes = guard.check([
        {"id": "exp.northstar.b1", "action": "kept"},
        {"id": "exp.meridian.b1", "action": "rewrote", "text": "Reworded bullet"},
        {"id": "exp.orion.b1", "action": "dropped"},
    ], MASTER)
    return tailor.build_cv_content(changes, MASTER)


def test_cv_pdf_is_a_real_pdf_file(tmp_path):
    path = pdf.cv_pdf(_content(), tmp_path / "cv.pdf")
    assert path.exists() and path.stat().st_size > 1000
    assert path.read_bytes().startswith(b"%PDF-")


def test_cv_pdf_accepts_a_writable_stream():
    import io
    buf = io.BytesIO()
    pdf.cv_pdf(_content(), buf)
    buf.seek(0)
    assert buf.read(5) == b"%PDF-"


def test_cv_pdf_uses_the_chosen_accent_color(tmp_path):
    navy = pdf.cv_pdf(_content(), tmp_path / "navy.pdf", accent="navy")
    teal = pdf.cv_pdf(_content(), tmp_path / "teal.pdf", accent="teal")
    assert navy.read_bytes() != teal.read_bytes()
