"""Operator-owned workspace setup. Never accepts an agent-selected path."""

import sqlite3
import time
from pathlib import Path

from .contracts import canonical, fail, validate_session
from .store import SCHEMA, Store


def example_policy():
    scope = {"principals": ["support-agent"], "tenant": "acme-lab", "project": "support",
             "ticket_ids": ["T-100"]}
    return {"schema": "ata-policy/v1", "rules": [
        {**scope, "id": "read-assigned", "effect": "ALLOW", "tool": "tickets.read"},
        {**scope, "id": "triage-assigned", "effect": "ALLOW", "tool": "tickets.set_status",
         "statuses": ["triaged"]},
        {**scope, "id": "review-resolution", "effect": "APPROVAL_REQUIRED",
         "tool": "tickets.set_status", "statuses": ["resolved"]},
        {**scope, "id": "never-close", "effect": "DENY", "tool": "tickets.set_status",
         "statuses": ["closed"]},
    ]}


def initialize(workspace, now=None):
    workspace = Path(workspace).resolve()
    if workspace.exists() and (not workspace.is_dir() or any(workspace.iterdir())):
        fail("WORKSPACE_EXISTS", "Choose a new or empty workspace; existing data is preserved")
    workspace.mkdir(parents=True, exist_ok=True)
    now = int(time.time()) if now is None else now
    store = Store(workspace / "authority.sqlite3")
    con = store.connect()
    try:
        con.executescript(SCHEMA)
        session = validate_session({"id": "support-agent", "principal": "support-agent",
                                    "tenant": "acme-lab", "project": "support",
                                    "expires_at": now + 1800})
        con.execute("BEGIN IMMEDIATE")
        con.execute("INSERT INTO sessions VALUES (?,?,?,?,?)", tuple(session.values()))
        con.executemany("INSERT INTO tickets VALUES (?,?,?,?,?)", [
            ("acme-lab", "support", "T-100", "open", 1),
            ("acme-lab", "support", "T-200", "open", 1),
            ("other-lab", "support", "T-100", "open", 1),
        ])
        store.append_audit(con, now, "WORKSPACE_INITIALIZED", mode="local_fixture")
        con.execute("COMMIT")
    finally:
        con.close()
    (workspace / "policy.json").write_text(canonical(example_policy()) + "\n", encoding="utf-8")
    return workspace


def open_workspace(workspace):
    workspace = Path(workspace).resolve()
    if not (workspace / "authority.sqlite3").is_file() or not (workspace / "policy.json").is_file():
        fail("WORKSPACE_MISSING", "Initialize a local workspace first")
    from .gateway import Gateway
    return Gateway(Store(workspace / "authority.sqlite3"), workspace / "policy.json")
