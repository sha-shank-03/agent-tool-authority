"""Two typed, real local ticket adapters. No external accounts or shell tools."""

from collections import Counter

from .contracts import fail


class TicketTools:
    def __init__(self):
        self.invocations = Counter()

    def execute(self, con, session, call):
        tool = call["tool"]
        args = call["arguments"]
        key = (session["tenant"], args["project"], args["ticket_id"])
        self.invocations[tool] += 1
        if tool == "tickets.set_status":
            changed = con.execute(
                "UPDATE tickets SET status=?,version=version+1 "
                "WHERE tenant=? AND project=? AND id=? AND version=?",
                (args["status"], *key, args["expected_version"]),
            ).rowcount
            if changed != 1:
                fail("STALE_RESOURCE", "The reviewed ticket version changed")
        row = con.execute("SELECT id,project,status,version FROM tickets "
                          "WHERE tenant=? AND project=? AND id=?", key).fetchone()
        if row is None:
            fail("SCOPE_DENIED", "Resource unavailable in this scope")
        return dict(row)
