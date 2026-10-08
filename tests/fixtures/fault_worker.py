"""Trusted test fixture producing bounded synthetic protocol faults, not a model."""

import json
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from agent_tool_authority.contracts import MAX_FRAME
from agent_tool_authority.harness import MAX_CALLS
from agent_tool_authority.mock_agent import calls

mode = sys.argv[1]
if mode == "oversized":
    sys.stdout.buffer.write(b"x" * (MAX_FRAME + 1) + b"\n")
    sys.stdout.buffer.flush()
elif mode == "malformed":
    print('{"tool":"tickets.read","tool":"tickets.set_status"}', flush=True)
elif mode == "non_utf8":
    sys.stdout.buffer.write(b"\xff\n")
    sys.stdout.buffer.flush()
elif mode == "excess_calls":
    for _ in range(MAX_CALLS + 1):
        print(json.dumps(calls()[0]), flush=True)
        if not sys.stdin.readline():
            break
elif mode == "unread_stdin":
    for _ in range(MAX_CALLS):
        print(json.dumps(calls()[0]), flush=True)
elif mode != "hung":
    raise SystemExit(2)

# The parent must kill/reap this direct child; it never spawns descendants.
threading.Event().wait(30)
