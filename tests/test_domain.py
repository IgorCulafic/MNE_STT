from copy import deepcopy
import pytest
from stt.domain import Conflict, edit, issues
from stt.transcripts import segment


def rows():
    return [segment(i + 1, t, i * 10., (i + 1) * 10., status="verified") for i, t in enumerate(["Śutra je lijep dan.", "Čujem đecu.", "Źenica, ćirilica, šuma, žar."])]


def test_shift_shared_boundaries_atomically():
    source = rows()
    result, changes = edit(source, "002", {"start": 12, "end": 22}, 30)
    assert [(s["start"], s["end"]) for s in result] == [(0, 12), (12, 22), (22, 30)]
    assert [s["text"] for s in result] == [s["text"] for s in source]
    assert [c["source"] for c in changes] == ["propagated", "direct", "propagated"]
    assert all(s["status"] == "unreviewed" and s["modified"] for s in result)
    assert source == rows()


@pytest.mark.parametrize("patch,expected", [({"start": 9}, [(0, 9), (9, 20), (20, 30)]), ({"end": 19}, [(0, 10), (10, 19), (19, 30)]), ({"start": 8, "end": 18}, [(0, 8), (8, 18), (18, 30)])])
def test_independent_boundaries_and_backward_shift(patch, expected):
    result, _ = edit(rows(), "002", patch, 30)
    assert [(s["start"], s["end"]) for s in result] == expected


@pytest.mark.parametrize("patch", [{"start": -1}, {"end": 31}, {"start": 20}, {"end": 10}, {"start": 0}, {"end": 30}, {"start": float('nan')}, {"end": float('inf')}])
def test_invalid_edit_preserves_input(patch):
    source = rows()
    old = deepcopy(source)
    with pytest.raises(Conflict):
        edit(source, "002", patch, 30)
    assert source == old


def test_gaps_preserved_until_overlap():
    source = [segment(1, "a", 0, 8), segment(2, "b", 10, 18), segment(3, "c", 20, 30)]
    result, _ = edit(source, "002", {"start": 9, "end": 19}, 30)
    assert result[0]["end"] == 8 and result[2]["start"] == 20
    result, _ = edit(source, "002", {"start": 7, "end": 21}, 30)
    assert result[0]["end"] == 7 and result[2]["start"] == 21


def test_unrelated_segments_do_not_move():
    source = rows() + [segment(4, "later", 31, 40)]
    result, _ = edit(source, "002", {"start": 12, "end": 22}, 40)
    assert result[3] == source[3]


def test_text_change_resets_verified_status_preserves_unicode():
    text = "č ć đ š ž ś ź — Ћирилица\n  untouched spacing  "
    result, changes = edit(rows(), "002", {"text": text}, 30)
    assert result[1]["text"] == text
    assert result[1]["status"] == "unreviewed"
    assert result[0] == rows()[0] and result[2] == rows()[2]
    assert len(changes) == 1


def test_import_issues_and_repair():
    source = rows()
    source[1]["start"] = 9
    assert issues(source, 30)
    result, _ = edit(source, "002", {"start": 10}, 30)
    assert not issues(result, 30)


def test_bad_status():
    with pytest.raises(Conflict):
        edit(rows(), "001", {"status": "finished"}, 30)


def test_cannot_verify_segment_overlapping_next():
    source = rows()
    source[0].update(end=11, status="unreviewed")
    with pytest.raises(Conflict):
        edit(source, "001", {"status": "verified"}, 30)
