from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from copy import deepcopy
import json
import os
from pathlib import Path
import threading
import uuid
from urllib.parse import quote
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from .domain import Conflict, issues
from .exports import bundle, encoded, manifest
from .media import chunk, decode, ffmpeg_executable, peaks
from .speech import align, transcribe
from .store import Store, dumps, now
from .transcripts import parse_transcript, render
from .chunking import options as chunk_options, plan as chunk_plan, silence_boundaries
from .models import MODELS

ROOT = Path(__file__).resolve().parent.parent


class Mutation(BaseModel):
    revision: int
    patch: dict = Field(default_factory=dict)


class ChunkRequest(BaseModel):
    revision: int
    options: dict = Field(default_factory=dict)


class ChunkApply(BaseModel):
    revision: int
    proposal_id: str


def create_app(data_root=None):
    pool = ThreadPoolExecutor(max_workers=2)
    @asynccontextmanager
    async def lifespan(app):
        yield
        pool.shutdown(wait=True)
    app = FastAPI(title="Montenegrin STT Review", lifespan=lifespan)
    store = Store(data_root or os.environ.get("STT_DATA_DIR", ROOT / "data"))
    job_lock = threading.Lock()
    jobs = {}
    jobs_dir = store.root / "jobs"
    jobs_dir.mkdir(exist_ok=True)
    for p in jobs_dir.glob("*.json"):
        job = json.loads(p.read_text(encoding="utf-8"))
        if job["status"] == "processing":
            job.update(status="failed", message="Processing was interrupted by a restart. Import the files again; originals remain in the data folder.")
            p.write_text(dumps(job), encoding="utf-8")
            store.log(job.get("project_id", job["id"]), "failure", error=job["message"])
        jobs[job["id"]] = job
    app.state.store = store
    app.state.jobs = jobs

    @app.middleware("http")
    async def local_only(request: Request, call_next):
        host = request.headers.get("host", "").split(":")[0]
        if host not in ("localhost", "127.0.0.1", "[", "testserver"):
            return JSONResponse({"detail": "This application is local-only."}, status_code=403)
        origin = request.headers.get("origin")
        if request.method not in ("GET", "HEAD", "OPTIONS") and origin and origin != str(request.base_url).rstrip("/"):
            return JSONResponse({"detail": "Cross-origin writes are disabled."}, status_code=403)
        return await call_next(request)

    @app.exception_handler(Conflict)
    async def conflict_handler(request, exc):
        return JSONResponse({"detail": str(exc)}, status_code=409)

    @app.exception_handler(KeyError)
    async def missing_handler(request, exc):
        return JSONResponse({"detail": "Project or job not found."}, status_code=404)

    def folder(pid):
        if not all(c in "0123456789abcdef-" for c in pid) or len(pid) != 36:
            raise KeyError(pid)
        return store.root / pid

    def update_job(jid, **patch):
        with job_lock:
            jobs[jid].update(patch)
            target = jobs_dir / f"{jid}.json"
            temp = target.with_suffix(".tmp")
            temp.write_text(dumps(jobs[jid]), encoding="utf-8")
            temp.replace(target)

    @app.get("/api/config")
    def config():
        import importlib.util
        return {"ffmpeg": bool(ffmpeg_executable()), "whisper": bool(importlib.util.find_spec("faster_whisper")),
                "models": MODELS, "languages": ["bs", "hr", "sr"]}

    @app.get("/api/projects")
    def projects():
        return store.list()

    def process(pid, media_name, transcript_name, settings):
        path = folder(pid)
        def report(message, percent):
            update_job(pid, message=message, percent=percent)
        try:
            report("Decoding and validating the original recording…", 8)
            duration = decode(path / "original-media", path / "audio.wav")
            rows = None
            if transcript_name:
                rows = parse_transcript((path / "original-transcript").read_bytes(), Path(transcript_name).suffix.lower(), duration)
                (path / "imported-transcript.json").write_bytes(encoded(rows))
            if rows is None or rows[0]["start"] is None:
                generated, words = transcribe(path / "audio.wav", settings, report)
                (path / "whisper-output.json").write_bytes(encoded({"segments": generated, "words": words}))
                rows = align(rows, words, duration) if rows is not None else generated
            original_rows = deepcopy(rows)
            chunking = settings.get("chunking", {"mode": "default"})
            if chunking["mode"] != "default":
                if issues(rows, duration):
                    raise Conflict("The transcript has invalid or overlapping timestamps. Import with Default chunking, repair the timing in Review, then apply chunking.")
                report("Preparing transcript chunks…", 89)
                pauses = silence_boundaries(path / "audio.wav", chunking["pause_seconds"]) if chunking["mode"] in ("pause", "sentence_pause") else None
                rows = chunk_plan(rows, duration, chunking, pauses)["segments"]
            report("Building the waveform and saving your project…", 92)
            (path / "peaks.json").write_bytes(encoded(peaks(path / "audio.wav")))
            invalid_ids = {x["id"] for x in issues(rows, duration)}
            for s in rows:
                if s["id"] in invalid_ids:
                    s["status"] = "flagged"
            state = {"id": pid, "name": Path(media_name).stem, "media_name": media_name,
                     "transcript_name": transcript_name, "duration": duration, "settings": settings, "segments": rows,
                     "original_segments": original_rows, "chunking": chunking}
            (path / "original-segments.json").write_bytes(encoded(original_rows))
            store.create(state)
            update_job(pid, status="complete", message="Ready to review", percent=100, project_id=pid)
        except Exception as exc:
            store.log(pid, "failure", error=str(exc), settings=settings)
            update_job(pid, status="failed", message=str(exc), percent=0)

    @app.post("/api/import")
    async def import_files(media: UploadFile = File(...), transcript: UploadFile | None = File(None),
                           language: str = Form("sr"), model: str = Form("base"),
                           chunk_mode: str = Form("default"), chunk_seconds: float = Form(10), pause_seconds: float = Form(.6)):
        if language not in ("bs", "hr", "sr") or model not in MODELS:
            raise Conflict("Choose Bosnian, Croatian or Serbian and a supported multilingual model.")
        chunking = chunk_options({"mode": chunk_mode, "seconds": chunk_seconds, "pause_seconds": pause_seconds})
        if chunk_mode in ("split", "merge"):
            raise Conflict("Manual splits and merges are available after import in Review.")
        pid = str(uuid.uuid4())
        path = folder(pid)
        path.mkdir()
        for upload, name in ((media, "original-media"), (transcript, "original-transcript")):
            if upload:
                with (path / name).open("wb") as out:
                    while data := await upload.read(1024 * 1024):
                        out.write(data)
                await upload.close()
        settings = {"language": language, "model": model, "backend": "faster-whisper", "task": "transcribe",
                    "device": "cpu", "compute_type": "int8", "alignment": "whisper-token-anchors (provisional)",
                    "workflow": "supplied-transcript" if transcript else "media-only", "chunking": chunking}
        names = {"media": media.filename, "transcript": transcript.filename if transcript else None}
        (path / "original-files.json").write_bytes(encoded(names))
        jobs[pid] = {"id": pid, "status": "processing", "message": "Files received", "percent": 2, "created_at": now(), "project_id": pid}
        update_job(pid)
        store.log(pid, "processing_settings", settings=settings, filenames=names)
        pool.submit(process, pid, media.filename or "Recording", transcript.filename if transcript else None, settings)
        return jobs[pid]

    @app.get("/api/jobs/{jid}")
    def job(jid: str):
        return jobs[jid]

    @app.get("/api/projects/{pid}")
    def project(pid: str):
        return store.get(pid)

    @app.patch("/api/projects/{pid}/segments/{sid}")
    def change(pid: str, sid: str, body: Mutation):
        try:
            return store.update(pid, body.revision, sid, body.patch)
        except Exception as exc:
            store.log(pid, "failure", body.revision, segment_ids=[sid], attempted_patch=body.patch, error=str(exc))
            raise

    def prepare_chunking(jid, pid, state, opts):
        try:
            pauses = silence_boundaries(folder(pid) / "audio.wav", opts["pause_seconds"]) if opts["mode"] in ("pause", "sentence_pause") else None
            proposal = chunk_plan(state["segments"], state["duration"], opts, pauses)
            proposal.update(project_id=pid, revision=state["revision"])
            (folder(pid) / f"proposal-{jid}.json").write_bytes(encoded(proposal))
            changed_ids = {c["id"] for c in proposal["changes"] if c["new"]}
            update_job(jid, status="complete", percent=100, message="Chunking preview ready",
                       preview={"proposal_id": jid, "revision": state["revision"], "options": opts,
                                "before_count": proposal["before_count"], "after_count": proposal["after_count"],
                                "changed_count": len(proposal["changes"]), "warnings": proposal["warnings"],
                                "segments": [s for s in proposal["segments"] if s["id"] in changed_ids][:100]})
        except Exception as exc:
            store.log(pid, "failure", state["revision"], error=str(exc), action_context="chunking_preview", settings=opts)
            update_job(jid, status="failed", message=str(exc))

    @app.post("/api/projects/{pid}/chunking/preview")
    def preview_chunking(pid: str, body: ChunkRequest):
        state = store.get(pid)
        if state["revision"] != body.revision:
            raise Conflict("Project changed. Reload before previewing chunking.")
        opts = chunk_options(body.options)
        jid = str(uuid.uuid4())
        jobs[jid] = {"id": jid, "project_id": pid, "status": "processing", "percent": 10, "message": "Preparing chunking preview…"}
        update_job(jid)
        pool.submit(prepare_chunking, jid, pid, state, opts)
        return jobs[jid]

    @app.post("/api/projects/{pid}/chunking/apply")
    def apply_chunking(pid: str, body: ChunkApply):
        job = jobs.get(body.proposal_id)
        if not job or job.get("project_id") != pid or job.get("status") != "complete" or "preview" not in job:
            raise Conflict("Generate a chunking preview for this project first.")
        proposal = json.loads((folder(pid) / f"proposal-{job['id']}.json").read_text(encoding="utf-8"))
        if proposal["revision"] != body.revision:
            raise Conflict("The preview revision does not match. Generate a fresh preview.")
        return store.apply_chunking(pid, body.revision, proposal)

    @app.post("/api/projects/{pid}/{action}")
    def history_action(pid: str, action: str, body: Mutation):
        if action not in ("undo", "redo"):
            raise HTTPException(404)
        return store.update(pid, body.revision, action=action)

    @app.get("/api/projects/{pid}/audit")
    def audit(pid: str):
        store.get(pid)
        return store.audit(pid)

    @app.get("/api/projects/{pid}/audio")
    def audio(pid: str):
        store.get(pid)
        return FileResponse(folder(pid) / "audio.wav", media_type="audio/wav")

    @app.get("/api/projects/{pid}/peaks")
    def waveform(pid: str):
        store.get(pid)
        return FileResponse(folder(pid) / "peaks.json", media_type="application/json")

    @app.get("/api/projects/{pid}/chunks/{sid}")
    def audio_chunk(pid: str, sid: str, revision: int):
        state, _ = store.snapshot(pid, revision, "chunk")
        s = next((s for s in state["segments"] if s["id"] == sid), None)
        if not s:
            raise KeyError(sid)
        filename = quote(f"segment-{sid}-r{revision}.wav")
        return Response(chunk(folder(pid) / "audio.wav", s["start"], s["end"]), media_type="audio/wav",
                        headers={"Content-Disposition": f"attachment; filename=\"segment-r{revision}.wav\"; filename*=UTF-8''{filename}", "Cache-Control": "no-store"})

    def export_zip(jid, state, audit):
        try:
            dest = folder(state["id"]) / f"export-{jid}.zip"
            bundle(state, audit, folder(state["id"]) / "audio.wav", dest)
            store.log(state["id"], "export_complete", state["revision"], format="zip", export_id=jid)
            update_job(jid, status="complete", percent=100, message="Research bundle ready", download=f"/api/download/{jid}")
        except Exception as exc:
            store.log(state["id"], "failure", state["revision"], error=str(exc), action_context="export")
            update_job(jid, status="failed", message=str(exc))

    @app.get("/api/projects/{pid}/export/{fmt}")
    def export(pid: str, fmt: str, revision: int):
        if fmt not in ("txt", "srt", "vtt", "json", "audit", "manifest", "zip"):
            raise HTTPException(404)
        state, audit = store.snapshot(pid, revision, fmt)
        if fmt == "zip":
            jid = str(uuid.uuid4())
            jobs[jid] = {"id": jid, "project_id": pid, "revision": revision, "status": "processing", "message": "Exporting corrected audio and research records…", "percent": 10}
            update_job(jid)
            pool.submit(export_zip, jid, deepcopy(state), deepcopy(audit))
            return jobs[jid]
        if fmt in ("txt", "srt", "vtt"):
            content = render(state["segments"], fmt).encode("utf-8")
        else:
            content = encoded(audit if fmt == "audit" else manifest(state) if fmt == "manifest" else {"project_id": pid, "revision": revision, "settings": state["settings"], "chunking": state.get("chunking", {"mode": "default"}), "segments": state["segments"]})
        store.log(pid, "export_complete", revision, format=fmt)
        ext = fmt if fmt in ("txt", "srt", "vtt") else "json"
        return Response(content, media_type="application/octet-stream", headers={"Content-Disposition": f'attachment; filename="{fmt}-r{revision}.{ext}"', "Cache-Control": "no-store"})

    @app.get("/api/download/{jid}")
    def download(jid: str):
        job = jobs[jid]
        if job["status"] != "complete" or "download" not in job:
            raise Conflict("Export is not ready.")
        return FileResponse(folder(job["project_id"]) / f"export-{jid}.zip", filename=f"stt-review-r{job['revision']}.zip")

    app.mount("/", StaticFiles(directory=ROOT / "web", html=True), name="web")
    return app
