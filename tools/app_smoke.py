"""Opt-in real-model end-to-end test. Requires test-results/jfk.flac."""
import os
from pathlib import Path
import sys
import time
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from fastapi.testclient import TestClient
from stt.app import create_app

root = Path(__file__).resolve().parent.parent
os.environ["STT_MODEL_CACHE"] = str(root / "data" / "models")
source = (root / "test-results" / "jfk.flac").read_bytes()


def await_project(client, files):
    response = client.post("/api/import", files=files, data={"language": "sr", "model": "base"})
    response.raise_for_status()
    jid = response.json()["id"]
    for _ in range(600):
        job = client.get("/api/jobs/" + jid).json()
        if job["status"] == "failed":
            raise AssertionError(job)
        if job["status"] == "complete":
            project = client.get("/api/projects/" + job["project_id"]).json()
            assert not project["issues"], project["issues"]
            return project
        time.sleep(.1)
    raise AssertionError("Model processing timed out")


with TestClient(create_app(root / "test-results" / "real-model-projects")) as client:
    generated = await_project(client, {"media": ("jfk.flac", source)})
    original_text = "\n".join(s["text"] for s in generated["segments"])
    aligned = await_project(client, {"media": ("jfk.flac", source), "transcript": ("reference.txt", original_text.encode("utf-8"))})
    assert "\n".join(s["text"] for s in aligned["segments"]) == original_text
    assert all(s["status"] == "flagged" for s in aligned["segments"])
    print(f"Real API import: {len(generated['segments'])} generated segments; alignment preserved all text and flagged {len(aligned['segments'])} segments.")
