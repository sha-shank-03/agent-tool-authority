"""Local state and audit; all protected local effects share this transaction."""

import sqlite3
from contextlib import contextmanager

from .contracts import canonical, parse_json

SCHEMA = """
CREATE TABLE sessions (
    id TEXT PRIMARY KEY, principal TEXT NOT NULL, tenant TEXT NOT NULL,
    project TEXT NOT NULL, expires_at INTEGER NOT NULL
);
CREATE TABLE tickets (
    tenant TEXT NOT NULL, project TEXT NOT NULL, id TEXT NOT NULL,
    status TEXT NOT NULL, version INTEGER NOT NULL CHECK(version > 0),
    PRIMARY KEY(tenant, project, id)
);
CREATE TABLE requests (
    id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES sessions(id),
    action_json TEXT NOT NULL, fingerprint TEXT NOT NULL, policy_digest TEXT NOT NULL,
    state TEXT NOT NULL, pending_expires_at INTEGER NOT NULL,
    grant_expires_at INTEGER, created_at INTEGER NOT NULL
);
CREATE TABLE audit (
    sequence INTEGER PRIMARY KEY AUTOINCREMENT, event_json TEXT NOT NULL
);
PRAGMA user_version = 1;
"""


class Store:
    def __init__(self, path):
        self.path = path

    def connect(self):
        con = sqlite3.connect(self.path, timeout=1.0, isolation_level=None)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys = ON")
        return con

    @contextmanager
    def transaction(self):
        con = self.connect()
        try:
            if con.execute("PRAGMA user_version").fetchone()[0] != 1:
                raise sqlite3.DatabaseError("Unsupported database version")
            con.execute("BEGIN IMMEDIATE")
            yield con
            con.execute("COMMIT")
        except BaseException:
            if con.in_transaction:
                con.execute("ROLLBACK")
            raise
        finally:
            con.close()

    def append_audit(self, con, now, event, **metadata):
        payload = {"schema": "ata-audit/v1", "timestamp": now, "event": event, **metadata}
        con.execute("INSERT INTO audit(event_json) VALUES (?)", (canonical(payload),))

    def audit(self):
        con = self.connect()
        try:
            return [{"sequence": row["sequence"], **parse_json(row["event_json"])}
                    for row in con.execute("SELECT sequence,event_json FROM audit ORDER BY sequence")]
        finally:
            con.close()
