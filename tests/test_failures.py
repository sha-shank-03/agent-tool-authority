"""M2: authorization and local transaction failure outcomes, using real SQLite."""

import itertools
import json
import sqlite3
import subprocess
import sys
import threading
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

from agent_tool_authority import OperatorService, initialize, open_workspace
from agent_tool_authority.contracts import (MAX_FRAME, AuthorityError, canonical, parse_json,
                                          validate_policy)
from agent_tool_authority.mock_agent import calls
from agent_tool_authority.tools import TicketTools
from agent_tool_authority.workspace import example_policy
from test_slice import temporary_workspace


class FailureTests(unittest.TestCase):
    def setUp(self):
        self.temp = temporary_workspace()
        self.workspace = Path(self.temp.name) / "failure"
        self.now = 1_800_000_000
        initialize(self.workspace, now=self.now)
        self.gateway = open_workspace(self.workspace)
        self.gateway.clock = lambda: self.now
        self.agent = self.gateway.agent("support-agent")
        self.operator = OperatorService(self.gateway)

    def tearDown(self):
        self.temp.cleanup()

    def pending(self):
        value = self.agent.submit(calls()[2])
        self.assertEqual("APPROVAL_REQUIRED", value["code"])
        return value

    def approved(self):
        value = self.pending()
        approved = self.operator.approve(value["request_id"], value["fingerprint"])
        self.assertEqual("APPROVED", approved["code"])
        return value, approved

    def state(self, pending):
        with self.gateway.store.transaction() as con:
            return con.execute("SELECT state FROM requests WHERE id=?",
                               (pending["request_id"],)).fetchone()[0]

    def assert_unchanged(self):
        with self.gateway.store.transaction() as con:
            actual = tuple(con.execute("SELECT status,version FROM tickets WHERE tenant='acme-lab' "
                                       "AND project='support' AND id='T-100'").fetchone())
        self.assertEqual(("open", 1), actual)

    def events(self, event):
        return [row for row in self.gateway.store.audit() if row["event"] == event]

    def test_session_just_before_and_at_expiration(self):
        self.now += 1799
        self.assertEqual("EXECUTED", self.agent.submit(calls()[0])["code"])
        self.now += 1
        self.assertEqual("SESSION_EXPIRED", self.agent.submit(calls()[0])["code"])
        self.assertEqual(1, self.gateway.tools.invocations["tickets.read"])
        self.assert_unchanged()

    def test_pending_expiration_at_boundary_cannot_approve(self):
        pending = self.pending()
        self.now = pending["pending_expires_at"]
        self.assertEqual("APPROVAL_EXPIRED", self.operator.approve(
            pending["request_id"], pending["fingerprint"])["code"])
        self.assertEqual("FAILED", self.state(pending))
        self.assertFalse(self.events("OPERATOR_APPROVED"))
        self.assert_unchanged()

    def test_approval_just_before_pending_deadline_cannot_extend_it(self):
        pending = self.pending()
        self.now = pending["pending_expires_at"] - 1
        approved = self.operator.approve(pending["request_id"], pending["fingerprint"])
        self.assertEqual(pending["pending_expires_at"], approved["grant_expires_at"])
        self.now += 1
        self.assertEqual("APPROVAL_EXPIRED", self.agent.resume(pending["request_id"])["code"])
        self.assertEqual(0, sum(self.gateway.tools.invocations.values()))
        self.assert_unchanged()

    def test_expired_pending_resume_reports_expiry_and_is_terminal(self):
        pending = self.pending()
        self.now = pending["pending_expires_at"]
        self.assertEqual("APPROVAL_EXPIRED", self.agent.resume(pending["request_id"])["code"])
        self.assertEqual("FAILED", self.state(pending))
        self.assertEqual(0, sum(self.gateway.tools.invocations.values()))
        self.assert_unchanged()

    def test_pending_and_grant_cannot_outlive_trusted_session(self):
        deadline = self.now + 1800
        self.now = deadline - 10
        pending, approved = self.approved()
        self.assertEqual(deadline, pending["pending_expires_at"])
        self.assertEqual(deadline, approved["grant_expires_at"])
        self.now = deadline
        self.assertEqual("SESSION_EXPIRED", self.agent.resume(pending["request_id"])["code"])
        self.assertEqual(0, sum(self.gateway.tools.invocations.values()))
        self.assert_unchanged()

    def test_grant_just_before_deadline_executes(self):
        pending, approved = self.approved()
        self.now = approved["grant_expires_at"] - 1
        self.assertEqual("EXECUTED", self.agent.resume(pending["request_id"])["code"])
        self.assertEqual("CONSUMED", self.state(pending))
        self.assertEqual(1, self.gateway.tools.invocations["tickets.set_status"])

    def test_grant_at_deadline_never_dispatches(self):
        pending, approved = self.approved()
        self.now = approved["grant_expires_at"]
        self.assertEqual("APPROVAL_EXPIRED", self.agent.resume(pending["request_id"])["code"])
        self.assertEqual("FAILED", self.state(pending))
        self.assertEqual(0, sum(self.gateway.tools.invocations.values()))
        self.assert_unchanged()

    def test_dispatch_rechecks_clock_after_initial_authorization(self):
        pending, approved = self.approved()
        moments = iter([approved["grant_expires_at"] - 1, approved["grant_expires_at"]])
        self.gateway.clock = lambda: next(moments)
        result = self.agent.resume(pending["request_id"])
        self.assertEqual("APPROVAL_EXPIRED", result["code"])
        self.assertEqual(0, sum(self.gateway.tools.invocations.values()))
        self.assertEqual("FAILED", self.state(pending))
        self.assertEqual("APPROVAL_EXPIRED", self.events("EXECUTION_REJECTED")[0]["code"])
        self.assert_unchanged()

    def test_clock_is_acquired_after_transaction_lock(self):
        pending, approved = self.approved()
        original = self.gateway.store.transaction

        @contextmanager
        def advance_before_yield():
            with original() as con:
                self.now = approved["grant_expires_at"]
                yield con

        with patch.object(self.gateway.store, "transaction", advance_before_yield):
            self.assertEqual("APPROVAL_EXPIRED", self.agent.resume(pending["request_id"])["code"])
        self.assertEqual(0, sum(self.gateway.tools.invocations.values()))
        self.assert_unchanged()

    def test_reject_is_terminal_without_mutation(self):
        pending = self.pending()
        self.assertEqual("FINGERPRINT_MISMATCH", self.operator.reject(
            pending["request_id"], "0" * 64)["code"])
        self.assertEqual("PENDING", self.state(pending))
        self.assertEqual("REJECTED", self.operator.reject(
            pending["request_id"], pending["fingerprint"])["code"])
        self.assertEqual("REJECTED", self.state(pending))
        self.assertEqual("APPROVAL_UNUSABLE", self.operator.approve(
            pending["request_id"], pending["fingerprint"])["code"])
        self.assertEqual("APPROVAL_UNUSABLE", self.agent.resume(pending["request_id"])["code"])
        self.assertEqual(1, len(self.events("OPERATOR_REJECTED")))
        self.assertEqual(0, sum(self.gateway.tools.invocations.values()))
        self.assert_unchanged()

    def test_wrong_session_cannot_use_or_inspect_action(self):
        pending, _ = self.approved()
        with self.gateway.store.transaction() as con:
            con.execute("INSERT INTO sessions VALUES (?,?,?,?,?)",
                        ("other-agent", "other-agent", "other-lab", "support", self.now + 1800))
        result = self.gateway.agent("other-agent").resume(pending["request_id"])
        self.assertEqual("REQUEST_UNAVAILABLE", result["code"])
        self.assertNotIn("request_id", result)
        self.assertNotIn("action", result)
        self.assertEqual("APPROVED", self.state(pending))
        self.assertEqual(0, sum(self.gateway.tools.invocations.values()))
        self.assert_unchanged()

    def test_approval_ttl_must_be_bounded_integer(self):
        pending = self.pending()
        for ttl in (0, -1, 61, True, 1.5, "60"):
            with self.subTest(ttl=ttl):
                self.assertEqual("INVALID_INPUT", self.operator.approve(
                    pending["request_id"], pending["fingerprint"], ttl)["code"])
        self.assertEqual("PENDING", self.state(pending))
        self.assert_unchanged()

    def test_policy_drift_at_approval_invalidates_pending_action(self):
        pending = self.pending()
        self.gateway.policy_path.write_text(canonical({"schema": "ata-policy/v1", "rules": []}))
        self.assertEqual("POLICY_CHANGED", self.operator.approve(
            pending["request_id"], pending["fingerprint"])["code"])
        self.assertEqual("FAILED", self.state(pending))
        self.gateway.policy_path.write_text(canonical(example_policy()))
        self.assertEqual("APPROVAL_UNUSABLE", self.agent.resume(pending["request_id"])["code"])
        self.assert_unchanged()

    def test_policy_drift_at_resume_invalidates_approved_action(self):
        pending, _ = self.approved()
        # A looser policy still requires a new review; the approved policy digest changed.
        policy = example_policy()
        policy["rules"][2]["effect"] = "ALLOW"
        self.gateway.policy_path.write_text(canonical(policy))
        self.assertEqual("POLICY_CHANGED", self.agent.resume(pending["request_id"])["code"])
        self.assertEqual("FAILED", self.state(pending))
        self.assertEqual(0, sum(self.gateway.tools.invocations.values()))
        self.assert_unchanged()

    def test_stored_action_drift_is_refused_at_approval_and_resume(self):
        for at_approval in (True, False):
            with self.subTest(at_approval=at_approval):
                pending = self.pending()
                if not at_approval:
                    self.operator.approve(pending["request_id"], pending["fingerprint"])
                with self.gateway.store.transaction() as con:
                    row = con.execute("SELECT action_json FROM requests WHERE id=?",
                                      (pending["request_id"],)).fetchone()
                    action = json.loads(row[0])
                    action["call"]["arguments"]["status"] = "closed"
                    con.execute("UPDATE requests SET action_json=? WHERE id=?",
                                (canonical(action), pending["request_id"]))
                result = (self.operator.approve(pending["request_id"], pending["fingerprint"])
                          if at_approval else self.agent.resume(pending["request_id"]))
                self.assertEqual("ACTION_CHANGED", result["code"])
                self.assertEqual("FAILED", self.state(pending))
        self.assertEqual(0, sum(self.gateway.tools.invocations.values()))
        self.assert_unchanged()

    def test_session_binding_drift_is_refused(self):
        pending, _ = self.approved()
        with self.gateway.store.transaction() as con:
            con.execute("UPDATE sessions SET principal='changed-principal' WHERE id='support-agent'")
        self.assertEqual("ACTION_CHANGED", self.agent.resume(pending["request_id"])["code"])
        self.assertEqual(0, sum(self.gateway.tools.invocations.values()))
        self.assert_unchanged()

    def test_resource_version_drift_before_operator_approval(self):
        pending = self.pending()
        with self.gateway.store.transaction() as con:
            con.execute("UPDATE tickets SET version=2 WHERE tenant='acme-lab' AND id='T-100'")
        self.assertEqual("STALE_RESOURCE", self.operator.approve(
            pending["request_id"], pending["fingerprint"])["code"])
        self.assertEqual("FAILED", self.state(pending))
        self.assertEqual(0, sum(self.gateway.tools.invocations.values()))

    def test_precedence_is_independent_of_order_and_reports_determining_rules(self):
        approval_rule = example_policy()["rules"][2]
        rules = [{**approval_rule, "id": effect.lower(), "effect": effect}
                 for effect in ("ALLOW", "APPROVAL_REQUIRED", "DENY")]
        for ordered in itertools.permutations(rules):
            self.gateway.policy_path.write_text(canonical({"schema": "ata-policy/v1", "rules": list(ordered)}))
            result = self.agent.submit(calls()[2])
            self.assertEqual("POLICY_DENIED", result["code"])
            self.assertEqual(["deny"], result["rule_ids"])
        for ordered in itertools.permutations(rules[:2]):
            self.gateway.policy_path.write_text(canonical({"schema": "ata-policy/v1", "rules": list(ordered)}))
            result = self.agent.submit(calls()[2])
            self.assertEqual("APPROVAL_REQUIRED", result["code"])
            self.assertEqual(["approval_required"], result["rule_ids"])
        self.gateway.policy_path.write_text(canonical({"schema": "ata-policy/v1", "rules": []}))
        result = self.agent.submit(calls()[0])
        self.assertEqual("POLICY_DENIED", result["code"])
        self.assertEqual([], result["rule_ids"])
        self.assertEqual(0, sum(self.gateway.tools.invocations.values()))
        self.assert_unchanged()

    def test_malformed_duplicate_oversized_json_and_strict_call_types(self):
        malformed = ["{", "", '{"a":1,"a":2}', '{"arguments":{"id":1,"id":2}}',
                     '{"a":NaN}', '{"a":1e400}', '"' + "x" * MAX_FRAME + '"', '"\ud800"']
        for raw in malformed:
            with self.subTest(raw_prefix=repr(raw[:30])):
                with self.assertRaises(AuthorityError):
                    parse_json(raw)
        for value in ([], None, {}, {**calls()[0], "schema": "ata-call/v2"},
                      {**calls()[0], "tool": []}, {**calls()[2], "now": self.now},
                      {**calls()[2], "arguments": {**calls()[2]["arguments"], "expected_version": True}},
                      {**calls()[2], "arguments": {**calls()[2]["arguments"], "status": []}}):
            with self.subTest(value=value):
                self.assertEqual("NOT_EXECUTED", self.agent.submit(value)["execution"])
        self.assertEqual(0, sum(self.gateway.tools.invocations.values()))
        self.assert_unchanged()

    def test_malformed_request_files_are_rejected_by_real_cli(self):
        for index, raw in enumerate(("{", '{"schema":"ata-call/v1","schema":"ata-call/v1"}',
                                     "x" * (MAX_FRAME + 1))):
            request = self.workspace / ("bad-" + str(index) + ".json")
            request.write_text(raw)
            result = subprocess.run([sys.executable, "-m", "agent_tool_authority", "submit",
                                     "--workspace", str(self.workspace), "--session", "support-agent",
                                     "--request", str(request)], capture_output=True, text=True, timeout=5)
            self.assertEqual(2, result.returncode)
            self.assertEqual("INVALID_INPUT", json.loads(result.stdout)["code"])
        self.assert_unchanged()
        self.assertFalse(self.events("TOOL_EXECUTED"))

    def test_invalid_policy_shapes_and_duplicate_scopes_fail_closed(self):
        base = example_policy()
        duplicate_id = {"schema": "ata-policy/v1", "rules": [base["rules"][0], base["rules"][0]]}
        invalid = [duplicate_id, {**base, "schema": "v2"}, {**base, "rules": "allow"},
                   {"schema": "ata-policy/v1", "rules": [{**base["rules"][0], "principals": ["*"]}]},
                   {"schema": "ata-policy/v1", "rules": [{**base["rules"][0], "ticket_ids": ["T-100", "T-100"]}]},
                   {"schema": "ata-policy/v1", "rules": base["rules"] * 17}]
        for policy in invalid:
            with self.subTest(policy=policy):
                with self.assertRaises(AuthorityError):
                    validate_policy(policy)
                self.gateway.policy_path.write_text(canonical(policy))
                self.assertEqual("POLICY_ERROR", self.agent.submit(calls()[0])["code"])
        self.assertEqual(0, sum(self.gateway.tools.invocations.values()))
        self.assert_unchanged()

    def test_adapter_mutates_then_raises_rolls_back_and_records_failure(self):
        class FailingTools(TicketTools):
            def execute(self, con, session, call):
                super().execute(con, session, call)
                raise RuntimeError("Synthetic adapter failure; never returned/logged")

        pending, _ = self.approved()
        self.gateway.tools = FailingTools()
        self.assertEqual("TOOL_ERROR", self.agent.resume(pending["request_id"])["code"])
        self.assert_unchanged()
        self.assertEqual("FAILED", self.state(pending))
        self.assertEqual(1, self.gateway.tools.invocations["tickets.set_status"])
        self.assertEqual(1, len(self.events("TOOL_FAILED")))
        self.assertFalse(self.events("TOOL_EXECUTED"))
        self.assertEqual("APPROVAL_UNUSABLE", self.agent.resume(pending["request_id"])["code"])
        self.assertNotIn("Synthetic", canonical(self.gateway.store.audit()))

    def test_audit_failure_rolls_back_ticket_and_consumption_and_can_retry(self):
        pending, _ = self.approved()
        before_audit = self.gateway.store.audit()
        append = self.gateway.store.append_audit

        def failing_audit(con, now, event, **metadata):
            if event == "TOOL_EXECUTED":
                raise sqlite3.OperationalError("Injected audit storage failure")
            append(con, now, event, **metadata)

        with patch.object(self.gateway.store, "append_audit", failing_audit):
            self.assertEqual("STORAGE_ERROR", self.agent.resume(pending["request_id"])["code"])
        self.assert_unchanged()
        self.assertEqual("APPROVED", self.state(pending))
        self.assertEqual(before_audit, self.gateway.store.audit())
        self.assertEqual("EXECUTED", self.agent.resume(pending["request_id"])["code"])
        self.assertEqual("CONSUMED", self.state(pending))
        self.assertEqual(1, len(self.events("TOOL_EXECUTED")))

    def test_unavailable_storage_claims_no_durable_audit_or_execution(self):
        before = self.gateway.store.audit()
        with patch.object(self.gateway.store, "connect", side_effect=sqlite3.OperationalError("Unavailable")):
            self.assertEqual("STORAGE_ERROR", self.agent.submit(calls()[0])["code"])
            self.assertFalse(self.gateway.record_harness_failure("support-agent", "DEADLINE"))
        self.assertEqual(0, sum(self.gateway.tools.invocations.values()))
        self.assertEqual(before, self.gateway.store.audit())
        self.assert_unchanged()

    def test_audit_failure_on_denial_does_not_invent_persisted_decision(self):
        before = self.gateway.store.audit()
        with patch.object(self.gateway.store, "append_audit", side_effect=sqlite3.OperationalError("Unavailable")):
            self.assertEqual("STORAGE_ERROR", self.agent.submit(calls()[1])["code"])
        self.assertEqual(0, sum(self.gateway.tools.invocations.values()))
        self.assertEqual(before, self.gateway.store.audit())
        self.assert_unchanged()

    def test_two_connections_race_one_grant_with_one_committed_mutation(self):
        pending, _ = self.approved()
        barrier = threading.Barrier(3)
        results, failures = [], []
        gateways = [open_workspace(self.workspace), open_workspace(self.workspace)]

        def resume(gateway):
            try:
                gateway.clock = lambda: self.now
                barrier.wait(timeout=3)
                results.append(gateway.agent("support-agent").resume(pending["request_id"]))
            except BaseException as exc:
                failures.append(exc)

        workers = [threading.Thread(target=resume, args=(gateway,)) for gateway in gateways]
        for worker in workers:
            worker.start()
        barrier.wait(timeout=3)
        for worker in workers:
            worker.join(timeout=3)
            self.assertFalse(worker.is_alive())
        self.assertEqual([], failures)
        self.assertEqual(["APPROVAL_CONSUMED", "EXECUTED"], sorted(result["code"] for result in results))
        self.assertEqual(1, sum(gateway.tools.invocations["tickets.set_status"] for gateway in gateways))
        with self.gateway.store.transaction() as con:
            self.assertEqual(("resolved", 2), tuple(con.execute(
                "SELECT status,version FROM tickets WHERE tenant='acme-lab' AND id='T-100'").fetchone()))
        self.assertEqual("CONSUMED", self.state(pending))
        self.assertEqual(1, len(self.events("TOOL_EXECUTED")))
        reopened = open_workspace(self.workspace)
        self.assertEqual(self.gateway.store.audit(), reopened.store.audit())
        reopened.clock = lambda: self.now
        self.assertEqual("APPROVAL_CONSUMED", reopened.agent("support-agent").resume(pending["request_id"])["code"])

    def test_pending_and_approved_grant_survive_store_reopen(self):
        pending = self.pending()
        reopened = open_workspace(self.workspace)
        reopened.clock = lambda: self.now
        operator = OperatorService(reopened)
        self.assertEqual("PENDING", operator.pending(pending["request_id"])["review"]["state"])
        self.assertEqual("APPROVED", operator.approve(pending["request_id"], pending["fingerprint"])["code"])
        third = open_workspace(self.workspace)
        third.clock = lambda: self.now
        self.assertEqual("EXECUTED", third.agent("support-agent").resume(pending["request_id"])["code"])
        self.assertEqual("CONSUMED", self.state(pending))


if __name__ == "__main__":
    unittest.main()
