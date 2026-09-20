"""Authoritative timing operations. Functions never mutate their input."""
from copy import deepcopy
import math
import unicodedata

STATUSES = {"unreviewed", "verified", "flagged", "incorrect"}


def comparable_text(text):
    return " ".join(unicodedata.normalize("NFC", text).split())


def correction_required(segment):
    return "rejection_text" in segment and comparable_text(segment["text"]) == comparable_text(segment["rejection_text"])


class Conflict(ValueError):
    pass


def issues(segments, duration):
    result = []
    for i, s in enumerate(segments):
        a, b = s["start"], s["end"]
        if not all(isinstance(v, (int, float)) and math.isfinite(v) for v in (a, b)):
            result.append({"id": s["id"], "message": "Timestamps must be finite numbers."})
        elif not 0 <= a < b <= duration:
            result.append({"id": s["id"], "message": "Require 0 ≤ start < end ≤ recording duration."})
        if i and segments[i - 1]["end"] > a:
            result.append({"id": s["id"], "message": f"Overlaps or is out of order with {segments[i - 1]['id']}."})
    return result


def edit(segments, segment_id, patch, duration):
    updated = deepcopy(segments)
    index = next((i for i, s in enumerate(updated) if s["id"] == segment_id), None)
    if index is None:
        raise Conflict("Unknown segment.")
    current, old = updated[index], segments[index]
    allowed = {"text", "start", "end", "status"}
    if set(patch) - allowed or not patch:
        raise Conflict("Provide text, start, end, or status.")
    if "status" in patch and patch["status"] not in STATUSES:
        raise Conflict("Unknown review status.")
    if "text" in patch and not isinstance(patch["text"], str):
        raise Conflict("Transcript text must be a string.")
    current.update(patch)
    if patch.get("status") == "incorrect":
        current["rejection_text"] = current["text"]
    if correction_required(current):
        if patch.get("status") in ("verified", "unreviewed", "flagged"):
            raise Conflict("This transcript was marked incorrect. Change its text before marking it correct; timing or whitespace-only edits do not count.")
        current["status"] = "incorrect"
    if patch.get("status") == "verified" and not comparable_text(current["text"]):
        raise Conflict("Enter transcript text before marking this segment correct.")
    for key in ("start", "end"):
        try:
            current[key] = round(float(current[key]), 3)
        except (TypeError, ValueError):
            raise Conflict("Timestamps must be numbers.")
        if not math.isfinite(current[key]):
            raise Conflict("Timestamps must be finite.")
    if any(key in patch for key in ("start", "end")):
        if index:
            previous = updated[index - 1]
            shared = abs(segments[index - 1]["end"] - old["start"]) < 0.0005
            if current["start"] != old["start"] and (shared or previous["end"] > current["start"]):
                previous["end"] = current["start"]
        if index + 1 < len(updated):
            following = updated[index + 1]
            shared = abs(old["end"] - segments[index + 1]["start"]) < 0.0005
            if current["end"] != old["end"] and (shared or current["end"] > following["start"]):
                following["start"] = current["end"]
    affected = []
    for before, after in zip(segments, updated):
        content_changed = any(before[k] != after[k] for k in ("text", "start", "end"))
        if content_changed:
            after.pop("word_spans", None)  # Word mappings no longer describe edited text/timing.
            after["modified"] = True
            if before["status"] == "verified" and after["status"] == "verified":
                after["status"] = "unreviewed"
        if before != after:
            affected.append({"id": after["id"], "source": "direct" if after["id"] == segment_id else "propagated", "old": before, "new": after})
    # Invalid imports are retained for repair. A repair must not introduce new
    # problems, and every segment touched by a timing edit must be valid.
    after_issues = issues(updated, duration)
    touched = {c["id"] for c in affected}
    if "start" in patch or "end" in patch:
        local = {s["id"] for s in updated[max(0, index - 1):index + 3]}
        bad = [x for x in after_issues if x["id"] in local]
        if bad:
            raise Conflict("Timing edit rejected: " + " ".join(x["id"] + ": " + x["message"] for x in bad))
    verification_ids = {current["id"]}
    if index + 1 < len(updated) and current["end"] > updated[index + 1]["start"]:
        verification_ids.add(updated[index + 1]["id"])
    if current["status"] == "verified" and any(x["id"] in verification_ids for x in after_issues):
        raise Conflict("Repair invalid timing before verifying this segment.")
    return updated, affected


def progress(segments):
    return {"total": len(segments), "reviewed": sum(s["status"] in ("verified", "incorrect") for s in segments),
            "modified": sum(bool(s.get("modified")) for s in segments),
            **{status: sum(s["status"] == status for s in segments) for status in STATUSES}}
