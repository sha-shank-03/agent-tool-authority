"""M1 semantic tests: inspect real state and adapter dispatch, not just labels."""

import tempfile
import unittest
from pathlib import Path

from agent_tool_authority import OperatorService, initialize, open_workspace
from agent_tool_authority.contracts import AuthorityError, validate_policy, validate_session
from agent_tool_authority.harness import demo
from agent_tool_authority.mock_agent import calls


def temporary_workspace():
    base = Path(__file__).resolve().parents[1] / "work" / "tests"
    base.mkdir(parents=True, exist_ok=True)
    temp = tempfile.TemporaryDirectory(dir=base)
    assert Path(temp.name).resolve().is_relative_to(base.resolve())
    return temp


class GatewaySliceTests(unittest.TestCase):
    def setUp(self):
        self.temp = temporary_workspace()
        self.workspace = Path(self.temp.name) / "fixture"
        self.now = 1_800_000_000
        initialize(self.workspace, now=self.now)
        self.gateway = open_workspace(self.workspace)
        self.gateway.clock = lambda: self.now
        self.agent = self.gateway.agent("support-agent")
        self.operator = OperatorService(self.gateway)

    def tearDown(self):
        self.temp.cleanup()

    def ticket(self, tenant="acme-lab"):
        with self.gateway.store.transaction() as con:
            return dict(con.execute("SELECT status,version FROM tickets WHERE tenant=? "
                                    "AND project='support' AND id='T-100'", (tenant,)).fetchone())

    def request_state(self, request_id):
        with self.gateway.store.transaction() as con:
            return con.execute("SELECT state FROM requests WHERE id=?", (request_id,)).fetchone()[0]

    def pending(self):
        result = self.agent.submit(calls()[2])
        self.assertEqual("APPROVAL_REQUIRED", result["decision"])
        return result

    def approve(self, pending):
        result = self.operator.approve(pending["request_id"], pending["fingerprint"])
        self.assertEqual("APPROVED", result["code"])
        return result

    def test_allowed_read_dispatches_real_adapter_without_mutation(self):
        result = self.agent.submit(calls()[0])
        self.assertEqual("EXECUTED", result["execution"])
        self.assertEqual("open", result["output"]["status"])
        self.assertEqual(1, self.gateway.tools.invocations["tickets.read"])
        self.assertEqual({"status": "open", "version": 1}, self.ticket())

    def test_denied_close_never_dispatches(self):
        result = self.agent.submit(calls()[1])
        self.assertEqual("DENY", result["decision"])
        self.assertEqual("NOT_EXECUTED", result["execution"])
        self.assertEqual(["never-close"], result["rule_ids"])
        self.assertEqual(0, sum(self.gateway.tools.invocations.values()))
        self.assertEqual({"status": "open", "version": 1}, self.ticket())
        self.assertFalse(any(row["event"] == "TOOL_EXECUTED" for row in self.gateway.store.audit()))

    def test_pending_and_operator_approval_do_not_mutate_or_dispatch(self):
        pending = self.pending()
        self.assertEqual("PENDING", self.request_state(pending["request_id"]))
        premature = self.agent.resume(pending["request_id"])
        self.assertEqual("APPROVAL_REQUIRED", premature["code"])
        review = self.operator.pending(pending["request_id"])["review"]
        self.assertEqual("resolved", review["action"]["call"]["arguments"]["status"])
        self.assertEqual(1, review["action"]["call"]["arguments"]["expected_version"])
        self.approve(pending)
        self.assertEqual("APPROVED", self.request_state(pending["request_id"]))
        self.assertEqual(0, sum(self.gateway.tools.invocations.values()))
        self.assertEqual({"status": "open", "version": 1}, self.ticket())

    def test_resume_commits_one_change_grant_consumption_and_audit(self):
        pending = self.pending()
        self.approve(pending)
        result = self.agent.resume(pending["request_id"])
        self.assertEqual("EXECUTED", result["execution"])
        self.assertEqual({"status": "resolved", "version": 2}, self.ticket())
        self.assertEqual("CONSUMED", self.request_state(pending["request_id"]))
        replay = self.agent.resume(pending["request_id"])
        self.assertEqual("APPROVAL_CONSUMED", replay["code"])
        self.assertEqual("NOT_EXECUTED", replay["execution"])
        self.assertEqual(1, self.gateway.tools.invocations["tickets.set_status"])
        self.assertEqual(2, self.ticket()["version"])
        audit = self.gateway.store.audit()
        executions = [row for row in audit if row["event"] == "TOOL_EXECUTED"]
        self.assertEqual(1, len(executions))
        self.assertEqual(pending["fingerprint"], executions[0]["fingerprint"])
        self.assertEqual(pending["request_id"], executions[0]["request_id"])
        self.assertEqual(2, executions[0]["version"])
        self.assertEqual(sorted(row["sequence"] for row in audit), [row["sequence"] for row in audit])

    def test_allowed_triage_mutates_only_bound_tenant(self):
        call = calls()[2]
        call["arguments"]["status"] = "triaged"
        result = self.agent.submit(call)
        self.assertEqual("EXECUTED", result["code"])
        self.assertEqual({"status": "triaged", "version": 2}, self.ticket())
        self.assertEqual({"status": "open", "version": 1}, self.ticket("other-lab"))
        self.assertEqual(1, self.gateway.tools.invocations["tickets.set_status"])

    def test_agent_cannot_assert_approval_or_invoke_operator_tool(self):
        self.assertFalse(hasattr(self.agent, "approve"))
        forged = calls()[2]
        forged["approved"] = True
        self.assertEqual("INVALID_INPUT", self.agent.submit(forged)["code"])
        forbidden = {"schema": "ata-call/v1", "tool": "authority.approve", "arguments": {}}
        self.assertEqual("UNKNOWN_TOOL", self.agent.submit(forbidden)["code"])
        identity = calls()[0]
        identity["principal"] = "operator"
        self.assertEqual("INVALID_INPUT", self.agent.submit(identity)["code"])
        self.assertEqual(0, sum(self.gateway.tools.invocations.values()))
        self.assertEqual(1, self.ticket()["version"])

    def test_exact_scope_default_deny_and_server_tenant_lookup(self):
        outside = calls()[0]
        outside["arguments"]["ticket_id"] = "T-200"
        self.assertEqual("POLICY_DENIED", self.agent.submit(outside)["code"])
        project = calls()[0]
        project["arguments"]["project"] = "other-project"
        self.assertEqual("SCOPE_DENIED", self.agent.submit(project)["code"])
        with self.gateway.store.transaction() as con:
            con.execute("DELETE FROM tickets WHERE tenant='acme-lab' AND id='T-100'")
        # The other tenant's ticket with the same ID cannot satisfy the request.
        self.assertEqual("SCOPE_DENIED", self.agent.submit(calls()[0])["code"])
        self.assertEqual(0, sum(self.gateway.tools.invocations.values()))
        self.assertEqual({"status": "open", "version": 1}, self.ticket("other-lab"))

    def test_pending_payload_is_copied_and_review_fingerprint_required(self):
        call = calls()[2]
        pending = self.agent.submit(call)
        call["arguments"]["status"] = "closed"
        self.assertEqual("FINGERPRINT_MISMATCH", self.operator.approve(pending["request_id"], "0" * 64)["code"])
        self.assertEqual("PENDING", self.request_state(pending["request_id"]))
        self.approve(pending)
        result = self.agent.resume(pending["request_id"])
        self.assertEqual("resolved", result["output"]["status"])
        self.assertEqual(2, self.ticket()["version"])

    def test_resource_version_is_rechecked_before_adapter_dispatch(self):
        pending = self.pending()
        self.approve(pending)
        with self.gateway.store.transaction() as con:
            con.execute("UPDATE tickets SET status='triaged',version=2 WHERE tenant='acme-lab' AND id='T-100'")
        result = self.agent.resume(pending["request_id"])
        self.assertEqual("STALE_RESOURCE", result["code"])
        self.assertEqual("FAILED", self.request_state(pending["request_id"]))
        self.assertEqual(0, sum(self.gateway.tools.invocations.values()))
        self.assertEqual({"status": "triaged", "version": 2}, self.ticket())

    def test_invalid_policy_and_invalid_session_fail_closed(self):
        self.gateway.policy_path.write_text('{"schema":"ata-policy/v1","rules":[]}', encoding="utf-8")
        self.assertEqual("POLICY_DENIED", self.agent.submit(calls()[0])["code"])
        self.gateway.policy_path.write_text("{}", encoding="utf-8")
        self.assertEqual("POLICY_ERROR", self.agent.submit(calls()[0])["code"])
        self.assertEqual(0, sum(self.gateway.tools.invocations.values()))
        with self.assertRaises(AuthorityError):
            validate_session({"id": "a", "principal": "p", "tenant": "t", "project": "p", "expires_at": True})
        with self.assertRaises(AuthorityError):
            validate_policy({"schema": "ata-policy/v1", "rules": [{"id": "unscoped"}]})

    def test_expired_session_has_no_tool_dispatch(self):
        self.now += 1800
        self.assertEqual("SESSION_EXPIRED", self.agent.submit(calls()[0])["code"])
        self.assertEqual(0, sum(self.gateway.tools.invocations.values()))

    def test_existing_workspace_is_preserved(self):
        before = self.gateway.policy_path.read_text()
        with self.assertRaises(AuthorityError) as raised:
            initialize(self.workspace)
        self.assertEqual("WORKSPACE_EXISTS", raised.exception.code)
        self.assertEqual(before, self.gateway.policy_path.read_text())
        self.assertEqual(1, self.ticket()["version"])


class MockJourneyTests(unittest.TestCase):
    def test_subprocess_mock_journey_asserts_real_local_results(self):
        with temporary_workspace() as temp:
            result = demo(Path(temp) / "demo")
            self.assertEqual("scripted_mock", result["mode"])
            self.assertEqual(0, result["paid_model_calls"])
            self.assertFalse(result["recorded_replay"])
            self.assertEqual({"tickets.read": 1, "tickets.set_status": 1}, result["tool_invocations"])
            self.assertEqual({"status": "open", "version": 1}, result["before_approval"])
            self.assertEqual({"status": "resolved", "version": 2}, result["after_approval"])
            self.assertEqual("APPROVAL_CONSUMED", result["replay"]["code"])


if __name__ == "__main__":
    unittest.main()
