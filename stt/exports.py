import json
import zipfile
from .domain import progress
from .media import chunk
from .transcripts import render


def encoded(value):
    return json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False).encode("utf-8")


def manifest(state):
    return {"project_id": state["id"], "revision": state["revision"], "name": state["name"],
            "duration": state["duration"], "source_file": state["media_name"], "settings": state["settings"],
            "chunking": state.get("chunking", {"mode": "default"}),
            "audio": {"format": "WAV PCM16", "sample_rate": 16000, "channels": 1, "context_padding": 0},
            "progress": progress(state["segments"]),
            "segments": [dict(s, audio_filename=f"audio/{s['id']}.wav") for s in state["segments"]]}


def bundle(state, audit, audio_path, output_path):
    # Write one chunk at a time, keeping long recordings out of RAM.
    with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as out:
        for fmt in ("txt", "srt", "vtt"):
            out.writestr(f"transcript.{fmt}", render(state["segments"], fmt).encode("utf-8"))
        out.writestr("transcript.json", encoded({"project_id": state["id"], "revision": state["revision"],
                                               "chunking": state.get("chunking", {"mode": "default"}), "segments": state["segments"]}))
        out.writestr("manifest.json", encoded(manifest(state)))
        out.writestr("audit.json", encoded(audit))
        out.writestr("progress.json", encoded(progress(state["segments"])))
        out.writestr("original-transcript.json", encoded(state["original_segments"]))
        for s in state["segments"]:
            out.writestr(f"audio/{s['id']}.wav", chunk(audio_path, s["start"], s["end"]))
