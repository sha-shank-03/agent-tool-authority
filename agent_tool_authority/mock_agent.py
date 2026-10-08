"""Scripted mock requests only. Does not call a model, database, or operator."""

import json
import sys


def calls():
    base = {"project": "support", "ticket_id": "T-100"}
    return [
        {"schema": "ata-call/v1", "tool": "tickets.read", "arguments": base},
        {"schema": "ata-call/v1", "tool": "tickets.set_status",
         "arguments": {**base, "status": "closed", "expected_version": 1}},
        {"schema": "ata-call/v1", "tool": "tickets.set_status",
         "arguments": {**base, "status": "resolved", "expected_version": 1}},
    ]


def main():
    for call in calls():
        print(json.dumps(call), flush=True)
        # Results come back from the host; none can confer operator permissions.
        if not sys.stdin.readline():
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
