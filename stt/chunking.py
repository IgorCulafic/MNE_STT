"""Text-preserving segmentation plans, independent of persistence and UI."""
from copy import deepcopy
import math
import re
import uuid
import wave
import numpy as np
from .domain import Conflict, issues, correction_required

MODES = {"default", "duration", "sentence", "pause", "sentence_pause", "split", "merge"}
ABBREVIATIONS = {"dr", "mr", "prof", "doc", "npr", "tj", "itd", "sl", "br", "god", "str", "ing", "sv"}


def options(raw):
    result = {"mode": raw.get("mode", "default"), "scope": raw.get("scope", "all"),
              "seconds": raw.get("seconds", 10), "pause_seconds": raw.get("pause_seconds", .6),
              "silence_threshold_db": -35}
    if result["mode"] not in MODES or result["scope"] not in ("all", "selected"):
        raise Conflict("Choose a supported chunking mode and scope.")
    for key, minimum, maximum in (("seconds", 1, 600), ("pause_seconds", .2, 5)):
        try:
            result[key] = float(result[key])
        except (TypeError, ValueError):
            raise Conflict(f"{key} must be a number.")
        if not math.isfinite(result[key]) or not minimum <= result[key] <= maximum:
            raise Conflict(f"{key} must be between {minimum} and {maximum}.")
    for key in ("segment_id", "time", "text_offset", "boundary_kind"):
        if key in raw:
            result[key] = raw[key]
    if result.get("boundary_kind", "manual") not in ("manual", "speaker_turn"):
        raise Conflict("Unknown manual boundary type.")
    return result


def sources(s):
    return s.get("source_ids", [s["id"]])


def changes_between(before, after, source="direct"):
    old, new = {s["id"]: s for s in before}, {s["id"]: s for s in after}
    return [{"id": sid, "old": old.get(sid), "new": new.get(sid), "source": source}
            for sid in dict.fromkeys([*old, *new]) if old.get(sid) != new.get(sid)]


def silence_boundaries(path, minimum=.6, threshold_db=-35):
    """Midpoints of interior low-energy runs. This is not speaker diarization."""
    threshold = 32768 * 10 ** (threshold_db / 20)
    found, quiet_start, was_speech = [], None, False
    with wave.open(str(path), "rb") as audio:
        if audio.getsampwidth() != 2 or audio.getnchannels() != 1:
            raise Conflict("Pause detection requires the project's normalized PCM recording.")
        rate, position = audio.getframerate(), 0
        while raw := audio.readframes(max(1, rate // 50)):
            samples = np.frombuffer(raw, dtype="<i2").astype(np.float32)
            t = position / rate
            quiet = float(np.sqrt(np.mean(samples * samples))) < threshold
            if quiet and quiet_start is None:
                quiet_start = t
            elif not quiet:
                if quiet_start is not None and was_speech and t - quiet_start >= minimum - .001:
                    found.append(round((quiet_start + t) / 2, 3))
                quiet_start = None
                was_speech = True
            position += len(samples)
    return found  # Leading/trailing silence does not create empty speech chunks.


def sentence_offsets(text):
    result = []
    for match in re.finditer(r'''[.!?…]+["»”’')\]]*\s+''', text):
        prefix = text[:match.start()]
        word = re.search(r"(\w+)$", prefix)
        if text[match.start()] == "." and word:
            token = word.group()
            if token.casefold() in ABBREVIATIONS or (len(token) == 1 and token.isupper()):
                continue
        if text[match.end():].strip():
            result.append(match.end())
    return result


def word_offsets(text):
    return [m.end() for m in re.finditer(r"\S+\s*", text) if text[m.end():].strip()]


def time_at_offset(s, offset):
    spans = s.get("word_spans", [])
    preceding = [w for w in spans if w["char_end"] <= offset]
    following = [w for w in spans if w["char_start"] >= offset]
    if preceding and following and not any(w["char_start"] < offset < w["char_end"] for w in spans):
        value = (preceding[-1]["end"] + following[0]["start"]) / 2
        if s["start"] < value < s["end"]:
            return round(value, 3), False
    return round(s["start"] + (s["end"] - s["start"]) * offset / max(1, len(s["text"])), 3), True


def offset_at_time(s, t):
    choices = word_offsets(s["text"])
    if not choices:
        return None, True
    candidates = [(offset, *time_at_offset(s, offset)) for offset in choices]
    offset, _, estimated = min(candidates, key=lambda item: abs(item[1] - t))
    return offset, estimated


def partition(s, cuts, mode):
    # Each cut contains an exact text offset, audio time and uncertainty flag.
    accepted, offset_before, time_before = [], 0, s["start"]
    for offset, t, estimated in sorted(cuts, key=lambda c: c[1]):
        if (offset is not None and offset_before < offset < len(s["text"])
                and time_before + .001 <= t <= s["end"] - .001
                and s["text"][offset_before:offset].strip() and s["text"][offset:].strip()):
            accepted.append((offset, round(t, 3), estimated))
            offset_before, time_before = offset, t
    if not accepted:
        return [deepcopy(s)]
    result, left_offset, left_time = [], 0, s["start"]
    uncertain = any(c[2] for c in accepted)
    for i, (right_offset, right_time, _) in enumerate([*accepted, (len(s["text"]), s["end"], False)]):
        row = deepcopy(s)
        row.update(id=s["id"] if i == 0 else "seg-" + uuid.uuid4().hex[:16],
                   text=s["text"][left_offset:right_offset], start=left_time, end=right_time,
                   modified=True, status="flagged" if uncertain or s["status"] == "flagged" else "unreviewed",
                   source_ids=list(sources(s)), chunking={"mode": mode, "estimated": uncertain})
        row.pop("word_spans", None)
        row.pop("rejection_text", None)
        spans = [dict(w, char_start=w["char_start"] - left_offset, char_end=w["char_end"] - left_offset)
                 for w in s.get("word_spans", [])
                 if left_offset <= w["char_start"] < w["char_end"] <= right_offset
                 and left_time <= w["start"] < w["end"] <= right_time]
        if spans:
            row["word_spans"] = spans
        result.append(row)
        left_offset, left_time = right_offset, right_time
    assert "".join(r["text"] for r in result) == s["text"]
    return result


def plan(segments, duration, raw_options, pauses=None):
    opts = options(raw_options)
    mode = opts["mode"]
    if issues(segments, duration):
        raise Conflict("Repair invalid timing and overlaps before changing chunk structure.")
    selected_id = opts.get("segment_id")
    index = next((i for i, s in enumerate(segments) if s["id"] == selected_id), None)
    if (opts["scope"] == "selected" or mode in ("split", "merge")) and index is None:
        raise Conflict("Select an existing segment first.")
    targets = segments[index:index + (2 if mode == "merge" else 1)] if mode in ("split", "merge") or opts["scope"] == "selected" else segments
    if mode != "default" and any(s["status"] == "incorrect" or correction_required(s) for s in targets):
        raise Conflict("Correct and approve the incorrect transcript before changing its chunk structure. You can still edit its text and timing.")
    result = deepcopy(segments)
    warnings = []
    if mode == "split":
        s = segments[index]
        try:
            t = round(float(opts["time"]), 3)
            offset = opts["text_offset"]
            if isinstance(offset, bool) or not isinstance(offset, int):
                raise ValueError()
        except (ValueError, TypeError, KeyError):
            raise Conflict("Provide a split time and a whole-number text cursor position.")
        if not math.isfinite(t) or not s["start"] < t < s["end"]:
            raise Conflict("The split time must fall strictly inside the selected segment.")
        if not 0 < offset < len(s["text"]) or not s["text"][:offset].strip() or not s["text"][offset:].strip():
            raise Conflict("Place the text cursor between the two nonempty transcript portions.")
        parts = partition(s, [(offset, t, False)], opts.get("boundary_kind", "manual"))
        if len(parts) != 2:
            raise Conflict("The split would create an empty chunk.")
        result[index:index + 1] = parts
    elif mode == "merge":
        if index + 1 >= len(segments):
            raise Conflict("There is no next segment to merge.")
        a, b = segments[index:index + 2]
        merged = deepcopy(a)
        merged.update(text=a["text"] + "\n" + b["text"], end=b["end"], modified=True,
                      status="flagged" if "flagged" in (a["status"], b["status"]) else "unreviewed",
                      source_ids=list(dict.fromkeys([*sources(a), *sources(b)])),
                      chunking={"mode": "manual_merge", "estimated": False})
        for key in ("word_spans", "confidence", "alignment", "rejection_text"):
            merged.pop(key, None)
        result[index:index + 2] = [merged]
        if b["start"] > a["end"]:
            warnings.append(f"The merged audio includes the {b['start'] - a['end']:.3f}s gap between these segments.")
    elif mode != "default":
        result = []
        for s in segments:
            if opts["scope"] == "selected" and s["id"] != selected_id:
                result.append(deepcopy(s))
                continue
            cuts = []
            if mode in ("sentence", "sentence_pause"):
                cuts += [(offset, *time_at_offset(s, offset)) for offset in sentence_offsets(s["text"])]
            times = []
            if mode == "duration":
                n = math.ceil((s["end"] - s["start"]) / opts["seconds"])
                times = [round(s["start"] + i * opts["seconds"], 3) for i in range(1, n)]
            elif mode in ("pause", "sentence_pause"):
                if pauses is None:
                    raise Conflict("Pause detection has not been run on the original recording.")
                times = [t for t in pauses if s["start"] < t < s["end"]]
            for t in times:
                offset, uncertain = offset_at_time(s, t)
                if offset is not None and not uncertain:
                    if mode == "duration":
                        t, uncertain = time_at_offset(s, offset)
                    else:
                        preceding = [w for w in s["word_spans"] if w["char_end"] <= offset]
                        following = [w for w in s["word_spans"] if w["char_start"] >= offset]
                        uncertain = not (preceding and following and preceding[-1]["end"] <= t <= following[0]["start"])
                cuts.append((offset, t, uncertain))
            result.extend(partition(s, cuts, mode))
    if issues(result, duration):
        raise Conflict("This plan would create invalid segment timing.")
    changes = changes_between(segments, result)
    if any(c["new"] and c["new"].get("chunking", {}).get("estimated") for c in changes):
        warnings.append("Some word-to-time boundaries are estimated. Affected chunks are flagged for manual review.")
    if mode in ("pause", "sentence_pause"):
        warnings.append("Pauses are detected from audio energy, not speaker identity. A change of person without a pause is not detected.")
    if mode not in ("split", "merge", "default"):
        warnings.append("Existing cue boundaries and gaps are retained. Chunks are split within each cue; words are not rewritten.")
    return {"segments": result, "changes": changes, "options": opts, "warnings": warnings,
            "before_count": len(segments), "after_count": len(result)}
