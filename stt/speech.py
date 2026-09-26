"""Whisper transcription and conservative matching of existing text to words."""
from copy import deepcopy
from difflib import SequenceMatcher
from pathlib import Path
import os
import re
import threading
from .domain import Conflict
from .transcripts import segment
from .models import model_cache

_inference_lock = threading.Lock()


def transcribe(path, settings, report):
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        raise Conflict("Whisper is not installed. Install requirements-whisper.txt using Python 3.11 or 3.12, then restart. You can still import a timestamped transcript.")
    report("Waiting for the transcription engine…", 20)
    with _inference_lock:
        report("Loading Whisper model (first use may download model weights)…", 22)
        cache = str(model_cache(Path(path).parent.parent))
        model = WhisperModel(settings["model"], device="cpu", compute_type="int8", download_root=cache)
        language = settings["language"]
        if language not in model.supported_languages:
            raise Conflict(f"Model {settings['model']} does not support {language}. Select a multilingual Whisper model; no language was substituted.")
        stream, info = model.transcribe(str(path), language=language, task="transcribe", word_timestamps=True, vad_filter=True)
        segments, words = [], []
        for s in stream:
            row = segment(len(segments) + 1, s.text, round(s.start, 3), round(s.end, 3), confidence=round(2.718281828 ** s.avg_logprob, 3))
            spans, position = [], 0
            for w in s.words or []:
                offset = s.text.find(w.word, position)
                if offset < 0:
                    spans = []
                    break
                spans.append({"char_start": offset + len(w.word) - len(w.word.lstrip()),
                              "char_end": offset + len(w.word.rstrip()), "start": round(w.start, 3), "end": round(w.end, 3)})
                position = offset + len(w.word)
            if spans:
                row["word_spans"] = spans
            segments.append(row)
            words.extend({"text": w.word, "start": w.start, "end": w.end} for w in (s.words or []))
            report(f"Transcribing {s.end:.1f} of {info.duration:.1f} seconds…", min(85, 25 + int(60 * s.end / max(info.duration, 1))))
        if not segments:
            raise Conflict("Whisper found no speech. Check the recording and selected language.")
        return segments, words


def tokens(text):
    return re.findall(r"\w+", text.casefold(), flags=re.UNICODE)


def align(existing, words, duration):
    """Exact token anchors + monotonic interpolation; never replace source text.

    This is an assistive alignment, not phonetic forced alignment. Every segment
    is flagged, and unmatched text has explicit provisional timing.
    """
    ref, owners = [], []
    for i, s in enumerate(existing):
        ts = tokens(s["text"])
        ref.extend(ts)
        owners.extend([i] * len(ts))
    recognized, positions = [], []
    for w in words:
        ts = tokens(w["text"])
        recognized.extend(ts)
        positions.extend([w] * len(ts))
    matches = {i: [] for i in range(len(existing))}
    matcher = SequenceMatcher(None, ref, recognized, autojunk=False)
    for block in matcher.get_matching_blocks():
        for k in range(block.size):
            matches[owners[block.a + k]].append(positions[block.b + k])
    # Propose internal boundaries from word matches; interpolate missing runs.
    n = len(existing)
    anchors = {0: 0.0, n: duration}
    for i in range(1, n):
        if matches[i]:
            anchors[i] = matches[i][0]["start"]
        elif matches[i - 1]:
            anchors[i] = matches[i - 1][-1]["end"]
    ordered = sorted(anchors)
    boundaries = [0.0] * (n + 1)
    for left, right in zip(ordered, ordered[1:]):
        for i in range(left, right + 1):
            boundaries[i] = anchors[left] + (anchors[right] - anchors[left]) * (i - left) / (right - left)
    if any(round(boundaries[i], 3) >= round(boundaries[i + 1], 3) for i in range(n)):
        # Explicitly labelled fallback keeps all text accessible for manual repair.
        boundaries = [duration * i / n for i in range(n + 1)]
        matches = {i: [] for i in range(n)}
    result = deepcopy(existing)
    for i, s in enumerate(result):
        confidence = len(matches[i]) / max(len(tokens(s["text"])), 1)
        s.update(start=round(boundaries[i], 3), end=round(boundaries[i + 1], 3), status="flagged",
                 alignment={"method": "whisper-token-anchors", "coverage": round(confidence, 3),
                            "note": "Provisional alignment; listen and correct timing." if matches[i] else "No reliable anchor. Timing interpolated; manual correction required."})
    return result
