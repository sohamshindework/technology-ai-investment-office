"""Local SQLite snapshots and human review records; no external service required.

For single-user demos only. This is not an authenticated compliance audit system.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from .reporting import bundle, settings


class Store:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as con:
            con.executescript("""
                CREATE TABLE IF NOT EXISTS runs (
                    id TEXT PRIMARY KEY, case_id TEXT NOT NULL, created_at TEXT NOT NULL,
                    settings TEXT NOT NULL, sha256 TEXT NOT NULL, bundle BLOB NOT NULL);
                CREATE TABLE IF NOT EXISTS reviews (
                    id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES runs(id),
                    initiative_id TEXT NOT NULL, reviewer TEXT NOT NULL, evidence TEXT NOT NULL,
                    decision TEXT NOT NULL, uncertainty TEXT NOT NULL, created_at TEXT NOT NULL);
            """)

    @contextmanager
    def connect(self):
        con = sqlite3.connect(self.path)
        try:
            con.execute("PRAGMA foreign_keys=ON")
            with con:
                yield con
        finally:
            con.close()

    def save(self, analysis) -> str:
        run_id = str(uuid4())
        data = bundle(analysis)
        with self.connect() as con:
            con.execute(
                "INSERT INTO runs VALUES (?, ?, ?, ?, ?, ?)",
                (
                    run_id,
                    analysis.case.id,
                    datetime.now(timezone.utc).isoformat(),
                    json.dumps(settings(analysis), allow_nan=False),
                    hashlib.sha256(data).hexdigest(),
                    data,
                ),
            )
        return run_id

    def load(self, run_id: str) -> bytes:
        with self.connect() as con:
            row = con.execute("SELECT bundle, sha256 FROM runs WHERE id=?", (run_id,)).fetchone()
        if row is None:
            raise KeyError(run_id)
        if hashlib.sha256(row[0]).hexdigest() != row[1]:
            raise ValueError("stored snapshot checksum mismatch")
        return row[0]

    def review(self, run_id, initiative_id, reviewer, evidence, decision, uncertainty):
        if decision not in {"approve assumptions", "request changes", "reject"}:
            raise ValueError("invalid decision")
        if not all(isinstance(v, str) and v.strip() for v in (reviewer, evidence, uncertainty)):
            raise ValueError("reviewer, evidence and remaining uncertainty are required")
        import io
        import zipfile

        with zipfile.ZipFile(io.BytesIO(self.load(run_id))) as z:
            state = json.loads(z.read("settings.json"))
        if initiative_id not in {i["id"] for i in state["inputs"]}:
            raise ValueError("unknown initiative")
        if decision == "approve assumptions":
            from .ai_act import screen

            initiative = next(i for i in state["inputs"] if i["id"] == initiative_id)
            if screen(initiative["ai_act"], state["compliance"]).excluded:
                raise ValueError("incomplete or excluded screening cannot be approved")
        with self.connect() as con:
            con.execute(
                "INSERT INTO reviews VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    str(uuid4()),
                    run_id,
                    initiative_id,
                    reviewer.strip(),
                    evidence.strip(),
                    decision,
                    uncertainty.strip(),
                    datetime.now(timezone.utc).isoformat(),
                ),
            )

    def reviews(self, run_id):
        with self.connect() as con:
            con.row_factory = sqlite3.Row
            return [dict(r) for r in con.execute("SELECT * FROM reviews WHERE run_id=? ORDER BY created_at", (run_id,))]
