"""SQLite transactions pair every revision with an audit record and history."""
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from .domain import Conflict, edit, issues, progress, correction_required
from .chunking import changes_between


def now():
    return datetime.now(timezone.utc).isoformat()


def dumps(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False)


class Store:
    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.db = self.root / "projects.sqlite3"
        with self.connect() as conn:
            conn.executescript('''
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS projects(id TEXT PRIMARY KEY, state TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS audit(seq INTEGER PRIMARY KEY AUTOINCREMENT, project_id TEXT, entry TEXT NOT NULL);
            ''')

    @contextmanager
    def connect(self):
        conn = sqlite3.connect(self.db, timeout=30)
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def _get(self, conn, pid):
        row = conn.execute("SELECT state FROM projects WHERE id=?", (pid,)).fetchone()
        if not row:
            raise KeyError(pid)
        return json.loads(row[0])

    def _save(self, conn, state):
        state["updated_at"] = now()
        conn.execute("INSERT OR REPLACE INTO projects VALUES (?,?)", (state["id"], dumps(state)))

    def _log(self, conn, pid, action, revision, **extra):
        entry = {"time": now(), "project_id": pid, "action": action, "revision": revision, **extra}
        conn.execute("INSERT INTO audit(project_id,entry) VALUES (?,?)", (pid, dumps(entry)))

    def create(self, state):
        state = deepcopy(state)
        state.update(revision=0, undo=[], redo=[], created_at=now())
        state.setdefault("original_segments", deepcopy(state["segments"]))
        with self.connect() as conn:
            self._save(conn, state)
            self._log(conn, state["id"], "import", 0, segment_ids=[s["id"] for s in state["segments"]], settings=state["settings"], issues=issues(state["segments"], state["duration"]))
        return self.public(state)

    def public(self, state):
        public = {k: v for k, v in state.items() if k not in ("undo", "redo")}
        public["segments"] = [dict(s, correction_required=correction_required(s)) if "rejection_text" in s else s for s in state["segments"]]
        public.update(can_undo=bool(state["undo"]), can_redo=bool(state["redo"]),
                      issues=issues(state["segments"], state["duration"]), progress=progress(state["segments"]))
        return public

    def get(self, pid):
        with self.connect() as conn:
            return self.public(self._get(conn, pid))

    def list(self):
        with self.connect() as conn:
            states = [json.loads(r[0]) for r in conn.execute("SELECT state FROM projects")]
        return [{k: s[k] for k in ("id", "name", "updated_at", "duration", "revision")} | {"progress": progress(s["segments"])}
                for s in sorted(states, key=lambda x: x["updated_at"], reverse=True)]

    def update(self, pid, revision, sid=None, patch=None, action="edit"):
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            state = self._get(conn, pid)
            if state["revision"] != revision:
                raise Conflict("This project changed in another tab. Reload before editing; your unsaved text is retained in this tab.")
            before = deepcopy(state["segments"])
            if action in ("undo", "redo"):
                source, target = ("undo", "redo") if action == "undo" else ("redo", "undo")
                if not state[source]:
                    raise Conflict(f"Nothing to {action}.")
                frame = state[source].pop()
                state[target].append(frame)
                state["segments"] = deepcopy(frame["before"] if action == "undo" else frame["after"])
                settings_key = "chunking_before" if action == "undo" else "chunking_after"
                if settings_key in frame:
                    state["chunking"] = deepcopy(frame[settings_key])
                changes = changes_between(before, state["segments"], "history")
            else:
                state["segments"], changes = edit(before, sid, patch, state["duration"])
                if not changes:
                    return self.public(state)
                state["undo"].append({"before": before, "after": deepcopy(state["segments"])})
                state["redo"] = []
                action = "timing" if any(k in patch for k in ("start", "end")) else "text" if "text" in patch else "status"
            state["revision"] += 1
            self._save(conn, state)
            self._log(conn, pid, action, state["revision"], segment_ids=[c["id"] for c in changes], changes=changes)
            result = self.public(state)
            result["adjusted_ids"] = [c["id"] for c in changes if c["source"] == "propagated"]
            return result

    def apply_chunking(self, pid, revision, proposal):
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            state = self._get(conn, pid)
            if state["revision"] != revision:
                raise Conflict("Project changed since this preview. Generate a new chunking preview before applying.")
            before, after = deepcopy(state["segments"]), deepcopy(proposal["segments"])
            if issues(after, state["duration"]) or len({s["id"] for s in after}) != len(after):
                raise Conflict("Chunking plan contains invalid boundaries or duplicate IDs.")
            changes = changes_between(before, after)
            if not changes:
                return self.public(state)
            previous = deepcopy(state.get("chunking", {"mode": "default"}))
            state["chunking"] = deepcopy(proposal["options"])
            state["undo"].append({"before": before, "after": after,
                                  "chunking_before": previous, "chunking_after": deepcopy(state["chunking"])})
            state["redo"] = []
            state["segments"] = after
            state["revision"] += 1
            self._save(conn, state)
            self._log(conn, pid, "chunking_" + proposal["options"]["mode"], state["revision"],
                      segment_ids=[c["id"] for c in changes], changes=changes,
                      settings=proposal["options"], warnings=proposal["warnings"])
            return self.public(state)

    def log(self, pid, action, revision=None, **extra):
        with self.connect() as conn:
            self._log(conn, pid, action, revision, **extra)

    def audit(self, pid, conn=None):
        if conn is not None:
            return [json.loads(r[0]) for r in conn.execute("SELECT entry FROM audit WHERE project_id=? ORDER BY seq", (pid,))]
        with self.connect() as connection:
            return self.audit(pid, connection)

    def snapshot(self, pid, revision, fmt):
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            state = self._get(conn, pid)
            if state["revision"] != revision:
                raise Conflict("Project changed. Refresh before exporting.")
            if fmt != "audit" and issues(state["segments"], state["duration"]):
                raise Conflict("Repair all invalid or overlapping timestamps before exporting.")
            self._log(conn, pid, "export_requested", revision, format=fmt, segment_ids=[s["id"] for s in state["segments"]])
            return self.public(state), self.audit(pid, conn)
