import json
import pytest
from stt.domain import Conflict
from stt.speech import align
from stt.transcripts import parse_transcript, render, segment


@pytest.mark.parametrize("fmt", ["srt", "vtt"])
def test_subtitle_roundtrip_preserves_unicode_and_multiline(fmt):
    rows = [segment(1, "  Č ć đ š ž ś ź\nЋирилица  ", 1.234, 5.678), segment(2, "  Hvala.  ", 6, 9)]
    parsed = parse_transcript(render(rows, fmt).encode("utf-8"), "." + fmt)
    assert parsed == rows


def test_txt_is_untimed_and_keeps_script():
    rows = parse_transcript("Śutra.\n\n  Ђе сте?  ".encode("utf-8"), ".txt")
    assert [s["text"] for s in rows] == ["Śutra.", "  Ђе сте?  "]
    assert all(s["start"] is None for s in rows)


def test_json_stable_ids():
    rows = parse_transcript(json.dumps({"segments": [{"id": "stable-A", "text": "a", "start": 1, "end": 2}]}).encode(), ".json")
    assert rows[0]["id"] == "stable-A"


@pytest.mark.parametrize("raw,suffix", [(b"", ".txt"), (b"\xff", ".txt"), (b"garbage", ".srt"), (b"WEBVTT", ".vtt"), (b'{"segments": [{"text": "a", "start": 1}]}', '.json'), (b'[]', '.json'), (b'[{"id":"../../x","text":"a"}]', '.json')])
def test_malformed_input(raw, suffix):
    with pytest.raises(Conflict):
        parse_transcript(raw, suffix)


def test_alignment_keeps_original_text_and_flags_estimates():
    rows = [segment(1, "Čujem đecu.", None, None), segment(2, "  Śutra!  ", None, None)]
    words = [{"text": "Čujem", "start": 0.2, "end": 1}, {"text": "đecu", "start": 1, "end": 2}, {"text": "Śutra", "start": 3, "end": 4}]
    aligned = align(rows, words, 5)
    assert [s["text"] for s in aligned] == [s["text"] for s in rows]
    assert all(s["status"] == "flagged" for s in aligned)
    assert aligned[0]["end"] == aligned[1]["start"] == 3
    assert rows[0]["start"] is None


def test_failed_alignment_is_explicit():
    aligned = align([segment(1, "unmatched", None, None), segment(2, "text", None, None)], [], 10)
    assert all(s["alignment"]["coverage"] == 0 for s in aligned)
    assert all("interpolated" in s["alignment"]["note"] for s in aligned)
