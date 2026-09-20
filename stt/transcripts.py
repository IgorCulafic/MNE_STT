"""UTF-8 transcript import and lossless text export."""
import json
import math
import re
from .domain import Conflict


def timestamp(value):
    if isinstance(value, (int, float)):
        return float(value)
    bits = str(value).replace(",", ".").split(":")
    if len(bits) not in (2, 3):
        raise Conflict(f"Invalid timestamp: {value}")
    try:
        nums = [float(x) for x in bits]
        if any(not math.isfinite(x) or x < 0 for x in nums) or nums[-1] >= 60 or (len(nums) == 3 and nums[-2] >= 60):
            raise ValueError()
        return sum(n * 60 ** i for i, n in enumerate(reversed(nums)))
    except ValueError:
        raise Conflict(f"Invalid timestamp: {value}")


def segment(number, text, start, end, **extra):
    return {"id": f"{number:03d}", "text": text, "start": start, "end": end,
            "status": "unreviewed", "modified": False, **extra}


def parse_transcript(raw, suffix, duration=None):
    try:
        text = raw.decode("utf-8-sig").replace("\r\n", "\n").replace("\r", "\n")
    except UnicodeDecodeError:
        raise Conflict("Transcript must be UTF-8 encoded. Save it as UTF-8 and try again.")
    if not text.strip():
        raise Conflict("Transcript is empty.")
    if suffix == ".txt":
        # Gemini-style timestamped TXT; blank lines belong to the cue body.
        headers = list(re.finditer(r"^\[([^\]\n]+?)\s+-\s+([^\]\n]+?)\][ \t]*$", text, re.MULTILINE))
        if headers:
            if text[:headers[0].start()].strip():
                raise Conflict("Unexpected text before the first TXT timestamp.")
            result = []
            for i, header in enumerate(headers):
                body = text[header.end():headers[i+1].start() if i+1 < len(headers) else len(text)].strip("\n")
                start = timestamp(header[1].strip())
                terminal = header[2].strip().lower() == "end"
                if not body.strip():
                    if terminal and i == len(headers)-1:
                        continue  # An empty closing marker is not spoken text.
                    raise Conflict("Timestamped TXT cue is missing transcript text.")
                if terminal and duration is None:
                    raise Conflict("An 'end' timestamp requires the recording duration.")
                end = duration if terminal else timestamp(header[2].strip())
                result.append(segment(len(result)+1, body, start, end))
            if not result:
                raise Conflict("No transcript text found between TXT timestamps.")
            return result
        return [segment(i + 1, line, None, None) for i, line in enumerate(text.split("\n")) if line.strip()]
    if suffix == ".json":
        try:
            data = json.loads(text)
            rows = data["segments"] if isinstance(data, dict) else data
            if not isinstance(rows, list) or not rows:
                raise ValueError()
            result = []
            for i, row in enumerate(rows):
                if not isinstance(row.get("text"), str):
                    raise ValueError()
                start, end = row.get("start"), row.get("end")
                if (start is None) != (end is None):
                    raise ValueError()
                if start is not None:
                    start, end = float(start), float(end)
                    if not math.isfinite(start) or not math.isfinite(end):
                        raise ValueError()
                sid = str(row.get("id", f"{i + 1:03d}"))
                if not re.fullmatch(r"[\w-]{1,80}", sid):
                    raise Conflict("JSON IDs must contain 1–80 letters, digits, underscores or hyphens.")
                result.append(segment(i + 1, row["text"], start, end, id=sid))
            if len({s["id"] for s in result}) != len(result):
                raise Conflict("JSON segment IDs must be unique.")
            if any(s["start"] is None for s in result) and not all(s["start"] is None for s in result):
                raise Conflict("JSON must have timing for every segment or for none.")
            return result
        except (ValueError, KeyError, TypeError, AttributeError):
            raise Conflict("Malformed JSON. Expected {segments: [{id, text, start, end}]} with numeric seconds.")
    if suffix not in (".srt", ".vtt"):
        raise Conflict("Supported transcript formats: TXT, SRT, VTT, JSON.")
    if suffix == ".vtt":
        if not text.startswith("WEBVTT"):
            raise Conflict("VTT files must start with WEBVTT.")
        text = text.split("\n", 1)[1] if "\n" in text else ""
    result = []
    for block in re.split(r"\n[ \t]*\n", text.strip("\n")):
        lines = block.split("\n")
        if suffix == ".vtt" and lines[0].split(" ")[0] in ("NOTE", "STYLE", "REGION"):
            continue
        timing_index = next((i for i, line in enumerate(lines[:2]) if "-->" in line), None)
        if timing_index is None or timing_index + 1 >= len(lines):
            raise Conflict("Malformed subtitle cue: missing timestamp or text.")
        times = lines[timing_index].split("-->")
        if len(times) != 2:
            raise Conflict("Malformed subtitle timestamp.")
        start = timestamp(times[0].strip())
        end = timestamp(times[1].strip().split()[0])
        result.append(segment(len(result) + 1, "\n".join(lines[timing_index + 1:]), start, end))
    if not result:
        raise Conflict("No subtitle cues found.")
    return result


def stamp(seconds, vtt=False):
    ms = round(seconds * 1000)
    hours, ms = divmod(ms, 3600000)
    minutes, ms = divmod(ms, 60000)
    secs, ms = divmod(ms, 1000)
    return f"{hours:02}:{minutes:02}:{secs:02}{'.' if vtt else ','}{ms:03}"


def render(segments, fmt):
    if fmt == "txt":
        return "\n".join(s["text"] for s in segments) + "\n"
    if fmt in ("srt", "vtt"):
        vtt = fmt == "vtt"
        return ("WEBVTT\n\n" if vtt else "") + "\n\n".join(
            f"{i + 1}\n{stamp(s['start'], vtt)} --> {stamp(s['end'], vtt)}\n{s['text']}"
            for i, s in enumerate(segments)) + "\n"
    raise Conflict("Unsupported export format.")
