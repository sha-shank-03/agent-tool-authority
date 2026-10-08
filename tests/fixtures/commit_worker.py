"""Trusted crash fixture: pause gateway transaction before/after actual COMMIT."""

import json
import sys
import threading
from contextlib import contextmanager
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from agent_tool_authority.gateway import Gateway
from agent_tool_authority.store import Store

workspace = Path(sys.argv[1]).resolve()
request_id, stage = sys.argv[2:4]
now = int(sys.argv[4])
marker = workspace / (stage + ".ready.json")


def pause(con):
    receipt = {"stage": stage, "inside_ticket_version": con.execute(
        "SELECT version FROM tickets WHERE tenant='acme-lab' AND id='T-100'").fetchone()[0],
        "inside_grant_state": con.execute("SELECT state FROM requests WHERE id=?", (request_id,)).fetchone()[0],
        "inside_execution_audit": sum(json.loads(row[0])["event"] == "TOOL_EXECUTED"
                                      for row in con.execute("SELECT event_json FROM audit"))}
    marker.write_text(json.dumps(receipt), encoding="utf-8")
    threading.Event().wait(30)


class CommitBarrierStore(Store):
    @contextmanager
    def transaction(self):
        with super().transaction() as con:
            yield con
            if stage == "before_commit":
                pause(con)  # Changes staged; parent's read connection sees the old state.
        if stage == "after_commit":
            con = self.connect()
            try:
                pause(con)  # Durable commit completed, caller still has no response.
            finally:
                con.close()


gateway = Gateway(CommitBarrierStore(workspace / "authority.sqlite3"), workspace / "policy.json",
                  clock=lambda: now)
result = gateway.agent("support-agent").resume(request_id)
print(json.dumps(result), flush=True)
