"""M2 bounded real child-process/pipe and local commit-interruption tests."""

import json
import sqlite3
import subprocess
import sys
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from agent_tool_authority import OperatorService, initialize, open_workspace
from agent_tool_authority.contracts import AuthorityError
from agent_tool_authority.harness import MAX_CALLS, _supervise, run_mock
from agent_tool_authority.mock_agent import calls
from test_slice import temporary_workspace

FIXTURES = Path(__file__).resolve().parent / "fixtures"
WORK = Path(__file__).resolve().parents[1] / "work"


class ProcessTests(unittest.TestCase):
    def setUp(self):
        self.temp = temporary_workspace()
        self.workspace = Path(self.temp.name) / "process"
        self.now = 1_800_000_000
        initialize(self.workspace, now=self.now)
        self.gateway = open_workspace(self.workspace)
        self.gateway.clock = lambda: self.now
        self.agent = self.gateway.agent("support-agent")

    def tearDown(self):
        self.temp.cleanup()

    def assert_cleaned(self, diagnostics):
        self.assertTrue(diagnostics["child_reaped"])
        self.assertIsNotNone(diagnostics["child_returncode"])
        self.assertFalse(diagnostics["reader_alive"])
        self.assertFalse(diagnostics["writer_alive"])

    def test_hung_oversized_malformed_and_excess_workers_are_reaped(self):
        receipts = []
        for mode, reason in (("hung", "DEADLINE"), ("oversized", "FRAME_LIMIT"),
                             ("malformed", "INVALID_FRAME"), ("non_utf8", "INVALID_FRAME"),
                             ("excess_calls", "CALL_LIMIT")):
            with self.subTest(mode=mode):
                diagnostics = {}
                before = self.gateway.tools.invocations["tickets.read"]
                started = time.monotonic()
                with self.assertRaises(AuthorityError) as raised:
                    _supervise(self.agent, [sys.executable, str(FIXTURES / "fault_worker.py"), mode],
                               timeout=1, diagnostics=diagnostics)
                elapsed = time.monotonic() - started
                self.assertEqual("HARNESS_ERROR", raised.exception.code)
                self.assertEqual(reason, diagnostics["reason"])
                self.assertLess(elapsed, 4.5)  # Exchange deadline + bounded cleanup, not a benchmark.
                self.assert_cleaned(diagnostics)
                actual = self.gateway.tools.invocations["tickets.read"] - before
                self.assertEqual(MAX_CALLS if mode == "excess_calls" else 0, actual)
                receipts.append({"mode": mode, "elapsed_seconds": elapsed, "adapter_calls": actual,
                                 **diagnostics})
        WORK.mkdir(exist_ok=True)
        (WORK / "m2-harness-receipts.json").write_text(json.dumps(receipts, indent=2), encoding="utf-8")

    def test_unread_stdin_expires_in_write_phase_and_writer_unblocks_after_kill(self):
        class SyntheticReplyHost:
            def submit(self, call):
                # Below 16 KiB/frame, above a small OS pipe buffer. This is test data.
                return {"payload": "x" * 15_000}

        diagnostics = {}
        started = time.monotonic()
        with self.assertRaises(AuthorityError) as raised:
            _supervise(SyntheticReplyHost(), [sys.executable, str(FIXTURES / "fault_worker.py"), "unread_stdin"],
                       timeout=1, diagnostics=diagnostics)
        elapsed = time.monotonic() - started
        self.assertEqual("HARNESS_ERROR", raised.exception.code)
        self.assertEqual("WRITE", diagnostics["last_phase"])
        self.assertEqual("DEADLINE", diagnostics["reason"])
        self.assertGreater(diagnostics["attempted_writes"], diagnostics["completed_writes"])
        self.assertLess(elapsed, 4.5)
        self.assert_cleaned(diagnostics)
        (WORK / "m2-stdin-stall-receipt.json").write_text(
            json.dumps({"elapsed_seconds": elapsed, **diagnostics}, indent=2), encoding="utf-8")

    def test_run_mock_failure_is_audited_after_direct_child_cleanup(self):
        created = []
        original_popen = subprocess.Popen

        def fixture_popen(command, **kwargs):
            process = original_popen([sys.executable, str(FIXTURES / "fault_worker.py"), "malformed"], **kwargs)
            created.append(process)
            return process

        with patch("agent_tool_authority.harness.subprocess.Popen", fixture_popen):
            with self.assertRaises(AuthorityError):
                run_mock(self.agent, lambda reason: self.gateway.record_harness_failure("support-agent", reason))
        self.assertEqual(1, len(created))
        self.assertIsNotNone(created[0].poll())
        rows = self.gateway.store.audit()
        failures = [row for row in rows if row["event"] == "HARNESS_FAILED"]
        self.assertEqual(1, len(failures))
        self.assertEqual("INVALID_FRAME", failures[0]["reason"])
        self.assertEqual(0, sum(self.gateway.tools.invocations.values()))

    @staticmethod
    def snapshot(workspace, request_id):
        con = sqlite3.connect(workspace / "authority.sqlite3", timeout=1)
        try:
            return {"ticket_version": con.execute(
                "SELECT version FROM tickets WHERE tenant='acme-lab' AND id='T-100'").fetchone()[0],
                "grant_state": con.execute("SELECT state FROM requests WHERE id=?", (request_id,)).fetchone()[0],
                "execution_audit": sum(json.loads(row[0])["event"] == "TOOL_EXECUTED"
                                       for row in con.execute("SELECT event_json FROM audit"))}
        finally:
            con.close()

    def test_termination_before_and_after_local_commit_has_distinct_persisted_outcomes(self):
        receipts = []
        for stage in ("before_commit", "after_commit"):
            with self.subTest(stage=stage):
                workspace = Path(self.temp.name) / stage
                initialize(workspace, now=self.now)
                gateway = open_workspace(workspace)
                gateway.clock = lambda: self.now
                pending = gateway.agent("support-agent").submit(calls()[2])
                approved = OperatorService(gateway).approve(pending["request_id"], pending["fingerprint"])
                self.assertEqual("APPROVED", approved["code"])
                options = {"creationflags": subprocess.CREATE_NO_WINDOW} if sys.platform == "win32" else {}
                process = subprocess.Popen([sys.executable, str(FIXTURES / "commit_worker.py"), str(workspace),
                                            pending["request_id"], stage, str(self.now)],
                                           stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, **options)
                marker = workspace / (stage + ".ready.json")
                try:
                    deadline = time.monotonic() + 5
                    while not marker.exists() and time.monotonic() < deadline and process.poll() is None:
                        time.sleep(0.01)
                    self.assertTrue(marker.exists(), "Crash checkpoint not reached")
                    # Reading the file after the child's flush is reliable for this tiny fixture;
                    # retry JSON decoding only if the parent observed the write before completion.
                    while True:
                        try:
                            inside = json.loads(marker.read_text())
                            break
                        except json.JSONDecodeError:
                            if time.monotonic() >= deadline:
                                raise
                            time.sleep(0.01)
                    self.assertEqual(2, inside["inside_ticket_version"])
                    self.assertEqual("CONSUMED", inside["inside_grant_state"])
                    self.assertEqual(1, inside["inside_execution_audit"])
                    visible_before_kill = self.snapshot(workspace, pending["request_id"])
                    process.kill()
                    process.wait(timeout=1)
                    self.assertIsNotNone(process.returncode)
                    persisted = self.snapshot(workspace, pending["request_id"])
                    expected = ({"ticket_version": 1, "grant_state": "APPROVED", "execution_audit": 0}
                                if stage == "before_commit" else
                                {"ticket_version": 2, "grant_state": "CONSUMED", "execution_audit": 1})
                    self.assertEqual(expected, visible_before_kill)
                    self.assertEqual(expected, persisted)
                    reopened = open_workspace(workspace)
                    reopened.clock = lambda: self.now
                    retry = reopened.agent("support-agent").resume(pending["request_id"])
                    self.assertEqual("EXECUTED" if stage == "before_commit" else "APPROVAL_CONSUMED",
                                     retry["code"])
                    final = self.snapshot(workspace, pending["request_id"])
                    self.assertEqual({"ticket_version": 2, "grant_state": "CONSUMED", "execution_audit": 1}, final)
                    receipts.append({"stage": stage, "child_returncode": process.returncode,
                                     "child_reaped": process.poll() is not None, "inside": inside,
                                     "visible_before_kill": visible_before_kill, "persisted_after_kill": persisted,
                                     "retry_code": retry["code"], "final": final})
                finally:
                    if process.poll() is None:
                        process.kill()
                    process.wait(timeout=1)
                    process.stderr.close()
        (WORK / "m2-commit-receipts.json").write_text(json.dumps(receipts, indent=2), encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
