import pytest
from stt.domain import Conflict
from stt.store import Store
from stt.transcripts import segment


def create(store):
    return store.create({"id": "test", "name": "test", "duration": 30, "media_name": "sample.wav", "settings": {"model": "base", "language": "sr"},
                         "segments": [segment(i + 1, "Č ć đ š ž ś ź", i * 10, (i + 1) * 10, status="verified") for i in range(3)]})


def test_atomic_undo_redo_save_reload_and_audit(tmp_path):
    store = Store(tmp_path)
    original = create(store)
    changed = store.update("test", 0, "002", {"start": 12, "end": 22})
    reloaded = Store(tmp_path).get("test")
    assert reloaded["segments"] == changed["segments"]
    assert reloaded["original_segments"] == original["segments"]
    undone = store.update("test", 1, action="undo")
    assert undone["segments"] == original["segments"]
    redone = store.update("test", 2, action="redo")
    assert redone["segments"] == changed["segments"]
    audit = store.audit("test")
    assert [a["action"] for a in audit] == ["import", "timing", "undo", "redo"]
    assert len(audit[1]["changes"]) == 3
    assert audit[1]["changes"][0]["source"] == "propagated"
    assert all(a["project_id"] == "test" and a["time"] for a in audit)


def test_conflict_does_not_save_partial_changes(tmp_path):
    store = Store(tmp_path)
    original = create(store)
    with pytest.raises(Conflict):
        store.update("test", 0, "002", {"start": 0})
    assert store.get("test")["segments"] == original["segments"]
    assert store.get("test")["revision"] == 0
    assert len(store.audit("test")) == 1


def test_revision_check_and_redo_invalidation(tmp_path):
    store = Store(tmp_path)
    create(store)
    store.update("test", 0, "002", {"text": "Нови текст ś ź"})
    with pytest.raises(Conflict):
        store.update("test", 0, "002", {"text": "stale"})
    store.update("test", 1, action="undo")
    branch = store.update("test", 2, "001", {"text": "another edit"})
    assert not branch["can_redo"]
    with pytest.raises(Conflict):
        store.snapshot("test", 1, "zip")
