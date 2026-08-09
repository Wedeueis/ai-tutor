from pipeline.adapters.filesystem.filesystem_scanner import FilesystemScanner


def test_scan_finds_files_and_hashes_content(tmp_path):
    (tmp_path / "note.md").write_text("hello", encoding="utf-8")
    (tmp_path / "README.md").write_text("ignore me", encoding="utf-8")

    scanner = FilesystemScanner()
    files = scanner.scan(str(tmp_path))

    assert len(files) == 1
    assert files[0].path.endswith("note.md")
    assert len(files[0].content_hash) == 64  # sha256 hex digest


def test_scan_ignores_hidden_files_and_dirs(tmp_path):
    hidden_dir = tmp_path / ".processed"
    hidden_dir.mkdir()
    (hidden_dir / "old.md").write_text("stale", encoding="utf-8")
    (tmp_path / ".hidden.md").write_text("stale", encoding="utf-8")
    (tmp_path / "real.md").write_text("real", encoding="utf-8")

    scanner = FilesystemScanner()
    files = scanner.scan(str(tmp_path))

    assert [f.path.endswith("real.md") for f in files] == [True]


def test_scan_on_missing_root_returns_empty(tmp_path):
    scanner = FilesystemScanner()
    assert scanner.scan(str(tmp_path / "does-not-exist")) == []


def test_read_text(tmp_path):
    path = tmp_path / "note.md"
    path.write_text("content here", encoding="utf-8")

    scanner = FilesystemScanner()
    assert scanner.read_text(str(path)) == "content here"


def test_same_content_yields_same_hash(tmp_path):
    (tmp_path / "a.md").write_text("same", encoding="utf-8")
    (tmp_path / "b.md").write_text("same", encoding="utf-8")

    scanner = FilesystemScanner()
    files = scanner.scan(str(tmp_path))

    hashes = {f.content_hash for f in files}
    assert len(hashes) == 1
