from copy import deepcopy
import pytest
from stt.domain import Conflict, edit, correction_required
from stt.chunking import plan
from stt.store import Store
from stt.transcripts import segment, parse_transcript


def sample():
    return [segment(1, "Čujem đecu.", 0, 10), segment(2, "Śutra.", 10, 20)]


def test_rejected_text_requires_real_change_and_can_be_corrected_later():
    rejected, _ = edit(sample(), "001", {"status":"incorrect"}, 20)
    assert correction_required(rejected[0])
    for patch in ({"status":"verified"}, {"status":"unreviewed"}, {"status":"flagged"},
                  {"text":"  Čujem  đecu.  ", "status":"verified"}):
        with pytest.raises(Conflict, match="Change its text"):
            edit(rejected,"001",patch,20)
    timed, _ = edit(rejected,"001",{"end":9},20)
    assert correction_required(timed[0])
    corrected, _ = edit(timed,"001",{"text":"Čujem djecu."},20)
    assert corrected[0]["status"] == "incorrect"
    assert not correction_required(corrected[0])
    approved, _ = edit(corrected,"001",{"status":"verified"},20)
    assert approved[0]["status"] == "verified"
    reverted, _ = edit(approved,"001",{"text":"Čujem đecu."},20)
    assert reverted[0]["status"] == "incorrect" and correction_required(reverted[0])


def test_new_rejection_resets_required_correction_and_blank_is_not_approvable():
    rows, _ = edit(sample(),"001",{"status":"incorrect"},20)
    rows, _ = edit(rows,"001",{"text":"Different"},20)
    rows, _ = edit(rows,"001",{"status":"incorrect"},20)
    assert correction_required(rows[0])
    rows, _ = edit(rows,"001",{"text":""},20)
    with pytest.raises(Conflict,match="Enter transcript"):
        edit(rows,"001",{"status":"verified"},20)


def test_timing_flag_does_not_force_text_change():
    rows=sample()
    rows[0]["status"]="flagged"
    result,_=edit(rows,"001",{"status":"verified"},20)
    assert result[0]["status"]=="verified"


def test_incorrect_chunks_cannot_bypass_correction_by_split_or_merge():
    rows,_=edit(sample(),"001",{"status":"incorrect"},20)
    for opts in ({"mode":"split","segment_id":"001","time":5,"text_offset":6},
                 {"mode":"merge","segment_id":"001"}, {"mode":"duration","seconds":3}):
        with pytest.raises(Conflict,match="Correct and approve"):
            plan(rows,20,opts)


def test_rejection_persists_and_undo_redo_restore_requirement(tmp_path):
    store=Store(tmp_path)
    store.create({"id":"test", "name":"test", "duration":20,"settings":{},"segments":sample()})
    store.update("test",0,"001",{"status":"incorrect"})
    store=Store(tmp_path)
    assert store.get("test")["segments"][0]["correction_required"]
    store.update("test",1,"001",{"text":"Corrected"})
    assert not store.get("test")["segments"][0]["correction_required"]
    store.update("test",2,action="undo")
    assert store.get("test")["segments"][0]["correction_required"]
    store.update("test",3,action="redo")
    assert not store.get("test")["segments"][0]["correction_required"]
    assert store.audit("test")[1]["changes"][0]["new"]["status"]=="incorrect"


def test_timestamped_gemini_txt_preserves_speakers_unicode_and_bad_timing():
    raw="[00:00:21 - 00:00:31]\n\nNarator: Śutra.\nDrugi red.\n\n[00:00:31 - 00:00:31]\n\nNovinarka: Đe?\n\n[00:00:40 - end]\n"
    rows=parse_transcript(raw.encode(),".txt",50)
    assert len(rows)==2
    assert rows[0]["text"]=="Narator: Śutra.\nDrugi red."
    assert (rows[0]["start"],rows[0]["end"])==(21,31)
    assert rows[1]["start"]==rows[1]["end"]==31
    assert rows[1]["text"]=="Novinarka: Đe?"


def test_txt_end_timestamp_with_text_uses_media_duration():
    rows=parse_transcript(b"[00:01 - end]\nHello", ".txt", 5)
    assert rows[0]["end"]==5
    with pytest.raises(Conflict):
        parse_transcript(b"[00:01 - end]\nHello", ".txt")
