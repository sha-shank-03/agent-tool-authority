"""Bounded local mock supervisor. Same-user processes are not sandboxed."""

import queue
import subprocess
import sys
import threading
import time

from .contracts import MAX_FRAME, AuthorityError, canonical, fail, parse_json
from .gateway import OperatorService
from .workspace import initialize, open_workspace

MAX_CALLS = 8
MAX_SECONDS = 5


def _supervise(agent, command, timeout=MAX_SECONDS, diagnostics=None):
    """Internal host-controlled command seam for trusted test fixtures, never model input.

    One monotonic deadline covers reads, write acknowledgements and child exit.
    Killing/reaping the direct child releases its pipe ends; cleanup gets up to
    three additional seconds. Trusted adapter execution is not a code sandbox.
    """
    diagnostics = diagnostics if diagnostics is not None else {}
    deadline = time.monotonic() + timeout
    options = {"creationflags": subprocess.CREATE_NO_WINDOW} if sys.platform == "win32" else {}
    if sys.platform == "linux":
        options["pipesize"] = 4096  # Small buffers exercise backpressure consistently.
    try:
        process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                   stderr=subprocess.DEVNULL, bufsize=0, **options)
    except OSError:
        fail("HARNESS_ERROR", "Cannot start the local mock worker")
    diagnostics.update(pid=process.pid, attempted_writes=0, completed_writes=0)
    frames = queue.Queue(maxsize=MAX_CALLS + 1)
    writes = queue.Queue(maxsize=1)
    acknowledgements = queue.Queue(maxsize=1)
    stopping = threading.Event()

    def remaining(phase):
        diagnostics["last_phase"] = phase
        value = deadline - time.monotonic()
        if value <= 0:
            diagnostics["reason"] = "DEADLINE"
            fail("HARNESS_ERROR", "Mock worker exceeded the supervisor deadline")
        return value

    def receive(channel, phase):
        try:
            return channel.get(timeout=remaining(phase))
        except queue.Empty:
            diagnostics["reason"] = "DEADLINE"
            fail("HARNESS_ERROR", "Mock worker exceeded the supervisor deadline")

    def deliver(channel, value):
        while not stopping.is_set() and time.monotonic() < deadline:
            try:
                channel.put(value, timeout=0.05)
                return
            except queue.Full:
                continue

    def read_frames():
        try:
            for _ in range(MAX_CALLS + 1):
                frame = process.stdout.readline(MAX_FRAME + 1)
                if not frame:
                    deliver(frames, None)
                    return
                deliver(frames, frame)
                if len(frame) > MAX_FRAME:
                    return
        except (OSError, ValueError):
            deliver(frames, b"")

    def write_responses():
        while not stopping.is_set():
            try:
                payload = writes.get(timeout=0.05)
            except queue.Empty:
                continue
            try:
                diagnostics["attempted_writes"] += 1
                offset = 0
                while offset < len(payload):
                    count = process.stdin.write(payload[offset:])
                    if not count:
                        raise BrokenPipeError("Worker input pipe closed")
                    offset += count
                process.stdin.flush()
                diagnostics["completed_writes"] += 1
                deliver(acknowledgements, True)
            except (OSError, ValueError):
                deliver(acknowledgements, False)
                return

    reader = threading.Thread(target=read_frames, daemon=True)
    writer = threading.Thread(target=write_responses, daemon=True)
    reader.start()
    writer.start()
    results = []
    try:
        for _ in range(MAX_CALLS + 1):
            frame = receive(frames, "READ")
            if frame is None:
                break
            if len(results) >= MAX_CALLS:
                diagnostics["reason"] = "CALL_LIMIT"
                fail("HARNESS_ERROR", "Mock worker exceeded call bounds")
            if len(frame) > MAX_FRAME:
                diagnostics["reason"] = "FRAME_LIMIT"
                fail("HARNESS_ERROR", "Mock worker exceeded frame/call bounds")
            try:
                call = parse_json(frame.decode("utf-8"))
            except (AuthorityError, UnicodeError):
                diagnostics["reason"] = "INVALID_FRAME"
                fail("HARNESS_ERROR", "Mock worker emitted invalid UTF-8 JSON")
            result = agent.submit(call)
            results.append(result)
            payload = (canonical(result) + "\n").encode("utf-8")
            if len(payload) > MAX_FRAME:
                diagnostics["reason"] = "RESPONSE_LIMIT"
                fail("HARNESS_ERROR", "Host response exceeds frame bounds")
            writes.put(payload, timeout=remaining("WRITE"))
            if not receive(acknowledgements, "WRITE"):
                diagnostics["reason"] = "PIPE_ERROR"
                fail("HARNESS_ERROR", "Mock worker input pipe failed")
        process.wait(timeout=remaining("EXIT"))
        if process.returncode != 0:
            diagnostics["reason"] = "CHILD_EXIT"
            fail("HARNESS_ERROR", "Mock worker failed")
        diagnostics["reason"] = "COMPLETED"
        return results
    except (subprocess.TimeoutExpired, queue.Full):
        diagnostics["reason"] = "DEADLINE"
        fail("HARNESS_ERROR", "Mock worker exceeded the supervisor deadline")
    except (BrokenPipeError, OSError):
        diagnostics["reason"] = "PIPE_ERROR"
        fail("HARNESS_ERROR", "Mock worker did not complete the local exchange")
    finally:
        stopping.set()
        if process.poll() is None:
            process.kill()
        process.wait(timeout=1)
        reader.join(timeout=1)
        writer.join(timeout=1)
        diagnostics.update(child_returncode=process.returncode, child_reaped=process.poll() is not None,
                           reader_alive=reader.is_alive(), writer_alive=writer.is_alive())
        # Do not close a stream being used by a live thread (close can itself block).
        if reader.is_alive() or writer.is_alive():
            fail("HARNESS_ERROR", "Worker pipe cleanup did not complete")
        process.stdin.close()
        process.stdout.close()


def run_mock(agent, failure_recorder=None):
    diagnostics = {}
    try:
        return _supervise(agent, [sys.executable, "-m", "agent_tool_authority.mock_agent"],
                          diagnostics=diagnostics)
    except AuthorityError:
        if failure_recorder is not None:
            failure_recorder(diagnostics.get("reason", "START_ERROR"))
        raise


def require(condition, message):
    if not condition:
        fail("DEMO_ASSERTION_FAILED", message)


def demo(workspace):
    initialize(workspace)
    gateway = open_workspace(workspace)
    agent = gateway.agent("support-agent")
    results = run_mock(agent, lambda reason: gateway.record_harness_failure("support-agent", reason))
    require(len(results) == 3, "Mock must produce three requests")
    read, denied, pending = results
    require(read["execution"] == "EXECUTED" and read["output"]["version"] == 1, "Read failed")
    require(denied["decision"] == "DENY" and denied["execution"] == "NOT_EXECUTED", "Close must be denied")
    require(pending["decision"] == "APPROVAL_REQUIRED", "Resolve must await operator approval")
    with gateway.store.transaction() as con:
        before = dict(con.execute("SELECT status,version FROM tickets WHERE tenant='acme-lab' "
                                  "AND project='support' AND id='T-100'").fetchone())
    require(before == {"status": "open", "version": 1}, "Denied/pending calls mutated the ticket")
    require(sum(gateway.tools.invocations.values()) == 1, "Denied/pending calls dispatched an adapter")
    operator = OperatorService(gateway)
    review = operator.pending(pending["request_id"])
    require(review["code"] == "REVIEW", "Operator review unavailable")
    # Explicit simulation of a separate trusted local operator, not agent approval.
    approval = operator.approve(pending["request_id"], review["review"]["fingerprint"])
    require(approval["code"] == "APPROVED", "Operator approval failed")
    executed = agent.resume(pending["request_id"])
    require(executed["execution"] == "EXECUTED", "Approved resolve did not execute")
    after = {key: executed["output"][key] for key in ("status", "version")}
    require(after == {"status": "resolved", "version": 2}, "Expected one version increment")
    replay = agent.resume(pending["request_id"])
    require(replay["code"] == "APPROVAL_CONSUMED", "Consumed approval replay must fail")
    require(gateway.tools.invocations["tickets.set_status"] == 1, "Replay dispatched the adapter")
    audit = gateway.store.audit()
    return {"mode": "scripted_mock", "model_execution": "none", "recorded_replay": False,
            "paid_model_calls": 0, "tools": "real_local_sqlite", "operator": "explicit_local_simulation",
            "workspace": str(gateway.policy_path.parent), "read": read, "denied_close": denied,
            "pending_resolve": pending, "operator_review": review, "operator_approval": approval,
            "approved_resume": executed, "replay": replay, "before_approval": before,
            "after_approval": after, "tool_invocations": dict(gateway.tools.invocations),
            "audit_rows": len(audit), "assertions": "passed"}
