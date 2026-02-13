from undistract_desktop.blocklist_store import BlocklistStore


def test_blocklist_store_roundtrip(tmp_path, monkeypatch):
    from undistract_desktop import blocklist_store as bs

    monkeypatch.setattr(bs, "APP_DIR", tmp_path)
    monkeypatch.setattr(bs, "STATE_FILE", tmp_path / "state.json")

    store = BlocklistStore()
    state = store.set_domains(["Example.com", "test.com", ""])
    assert "example.com" in state.domains
    assert "test.com" in state.domains

    state = store.set_blocking(True)
    assert state.blocking is True

    loaded = store.load()
    assert loaded.blocking is True
    assert "example.com" in loaded.domains
