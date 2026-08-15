import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from jobagent.documents import render as render_module


@pytest.fixture(autouse=True)
def stub_save_dialog(monkeypatch):
    """Never let tests pop the real OS 'Save As' dialog from accept_document()."""
    def fake_ask_save_path(default_dir, default_filename):
        Path(default_dir).mkdir(parents=True, exist_ok=True)
        return Path(default_dir) / default_filename

    monkeypatch.setattr(render_module, "ask_save_path", fake_ask_save_path)
