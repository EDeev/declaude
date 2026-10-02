import json
import shutil
from pathlib import Path

import pytest

from declaude import DataLoader, MappingManager, SiteBuilder
from declaude.cli import main

FIXTURE = Path(__file__).parent / "fixtures" / "backup"


@pytest.fixture
def archive(tmp_path):
    loader = DataLoader(FIXTURE)
    loader.load()
    mapping = MappingManager(tmp_path / "mapping.json")
    mapping.load()
    mapping.assign("c-1", "p-1")
    SiteBuilder(tmp_path / "out", loader, mapping).build_all()
    return tmp_path / "out"


def test_full_build_creates_all_pages(archive):
    for rel in ("index.html", "all_conversations.html", "projects/p-1/index.html",
                "conversations/c-1.html", "conversations/c-2.html", "conversations/c-3.html",
                "assets/style.css", "assets/app.js"):
        assert (archive / rel).is_file(), rel


def test_conversation_page_content(archive):
    page = (archive / "conversations" / "c-1.html").read_text(encoding="utf-8")
    assert "Нормализация до 3НФ" in page
    assert "<table" in page
    assert 'href="https://www.postgresql.org/docs/"' in page
    assert "javascript:" not in page
    assert "<script>alert" not in page


def test_project_page_lists_assigned_conversation(archive):
    page = (archive / "projects" / "p-1" / "index.html").read_text(encoding="utf-8")
    assert "Курсовая по базам данных" in page
    assert "c-1.html" in page and "c-2.html" not in page


def test_cli_build_and_map(tmp_path, monkeypatch):
    src = tmp_path / "backup"
    shutil.copytree(FIXTURE, src)
    out, mp = tmp_path / "out", tmp_path / "mapping.json"
    monkeypatch.setattr("sys.argv", ["declaude", "--build", "--source", str(src), "--output", str(out), "--mapping", str(mp)])
    main()
    assert (out / "index.html").is_file()
    monkeypatch.setattr("sys.argv", ["declaude", "--map", "c-2", "p-1", "--source", str(src), "--output", str(out), "--mapping", str(mp)])
    main()
    assert json.loads(mp.read_text(encoding="utf-8")).get("c-2") == "p-1"
