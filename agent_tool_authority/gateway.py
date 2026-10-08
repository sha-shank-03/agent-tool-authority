"""Enforcement belongs here, outside model-generated requests."""

import getpass
import secrets
import sqlite3
import time

from .contracts import (AuthorityError, digest, fail, identifier, integer, parse_json,
                        validate_call, validate_policy, validate_session)
from .tools import TicketTools


def response(decision, code, execution="NOT_EXECUTED", **metadata):
    return {"schema": "ata-result/v1", "decision": decision, "code": code,
            "execution": execution, **metadata}


def error_result(code):
    operational = {"INVALID_INPUT", "STORAGE_ERROR", "POLICY_ERROR", "TOOL_ERROR", "HARNESS_ERROR",
                   "WORKSPACE_EXISTS", "WORKSPACE_MISSING", "DEMO_ASSERTION_FAILED"}
    decision = "ERROR" if code in operational else "DENY"
    if code == "APPROVAL_REQUIRED":
        decision = "APPROVAL_REQUIRED"
    return response(decision, code)


class AgentFacade:
    """Bind in trusted host code. Expose only these two methods to a model."""

    def __init__(self, gateway, session_id):
        self.__gateway = gateway
        self.__session_id = identifier(session_id)

    def submit(self, call):
        return self.__gateway.submit(self.__session_id, call)

    def resume(self, request_id):
        return self.__gateway.resume(self.__session_id, request_id)


class Gateway:
    def __init__(self, store, policy_path, tools=None, clock=None):
        self.store = store
        self.policy_path = policy_path
        self.tools = tools if tools is not None else TicketTools()
        self.clock = clock if clock is not None else lambda: int(time.time())

    def agent(self, session_id):
        return AgentFacade(self, session_id)

    def _policy(self):
        try:
            with self.policy_path.open(encoding="utf-8") as stream:
                raw = stream.read(65_537)
            return validate_policy(parse_json(raw, maximum=65_536))
        except (AuthorityError, OSError, UnicodeError) as exc:
            raise AuthorityError("POLICY_ERROR", "Policy unavailable or invalid") from exc

    def _session(self, con, session_id, now):
        row = con.execute("SELECT * FROM sessions WHERE id=?", (session_id,)).fetchone()
        if row is None:
            fail("SESSION_UNAVAILABLE", "Session unavailable")
        session = validate_session(dict(row))
        if now >= session["expires_at"]:
            fail("SESSION_EXPIRED", "Session expired")
        return session

    def _scope(self, con, session, call):
        args = call["arguments"]
        if args["project"] != session["project"]:
            fail("SCOPE_DENIED", "Resource unavailable in this scope")
        row = con.execute("SELECT version FROM tickets WHERE tenant=? AND project=? AND id=?",
                          (session["tenant"], args["project"], args["ticket_id"])).fetchone()
        if row is None:
            fail("SCOPE_DENIED", "Resource unavailable in this scope")
        if call["tool"] == "tickets.set_status" and row["version"] != args["expected_version"]:
            fail("STALE_RESOURCE", "The reviewed ticket version changed")

    @staticmethod
    def _metadata(session, call, request_id, fingerprint, policy_hash, rules):
        return {"request_id": request_id, "session_id": session["id"],
                "principal": session["principal"], "tenant": session["tenant"],
                "project": session["project"], "tool": call["tool"],
                "ticket_id": call["arguments"]["ticket_id"], "fingerprint": fingerprint,
                "policy_digest": policy_hash, "rule_ids": rules}

    def _execute(self, con, now, session, call, metadata, consume=False):
        con.execute("SAVEPOINT local_tool")
        dispatched = False
        try:
            now = self.clock()
            if now >= session["expires_at"]:
                fail("SESSION_EXPIRED", "Session expired before dispatch")
            if consume:
                row = con.execute("SELECT pending_expires_at,grant_expires_at FROM requests WHERE id=?",
                                  (metadata["request_id"],)).fetchone()
                if now >= min(row["pending_expires_at"], row["grant_expires_at"]):
                    fail("APPROVAL_EXPIRED", "Approval expired before dispatch")
            dispatched = True
            output = self.tools.execute(con, session, call)
            if consume:
                con.execute("UPDATE requests SET state='CONSUMED' WHERE id=?",
                            (metadata["request_id"],))
            self.store.append_audit(con, now, "TOOL_EXECUTED", **metadata,
                                    decision="ALLOW", code="EXECUTED", version=output["version"])
            con.execute("RELEASE SAVEPOINT local_tool")
            return response("ALLOW", "EXECUTED", "EXECUTED", **metadata, output=output)
        except sqlite3.Error:
            # Storage/audit failure rolls back the enclosing transaction too.
            raise
        except Exception as exc:
            con.execute("ROLLBACK TO SAVEPOINT local_tool")
            con.execute("RELEASE SAVEPOINT local_tool")
            if consume:
                con.execute("UPDATE requests SET state='FAILED' WHERE id=?",
                            (metadata["request_id"],))
            code = exc.code if isinstance(exc, AuthorityError) else "TOOL_ERROR"
            self.store.append_audit(con, now, "TOOL_FAILED" if dispatched else "EXECUTION_REJECTED",
                                    **metadata, code=code)
            return {**error_result(code), **metadata}

    def submit(self, session_id, raw_call):
        from .contracts import canonical, evaluate
        try:
            identifier(session_id)
            policy = self._policy()
            with self.store.transaction() as con:
                now = self.clock()
                try:
                    session = self._session(con, session_id, now)
                    call = validate_call(raw_call)
                    self._scope(con, session, call)
                except AuthorityError as exc:
                    self.store.append_audit(con, now, "CALL_REJECTED", session_id=session_id,
                                            code=exc.code)
                    return error_result(exc.code)
                policy_hash = digest(policy)
                action = {"schema": "ata-action/v1", "session": session,
                          "call": call, "policy_digest": policy_hash}
                fingerprint = digest(action)
                request_id = secrets.token_hex(12)
                effect, rules = evaluate(policy, session, call)
                metadata = self._metadata(session, call, request_id, fingerprint, policy_hash, rules)
                self.store.append_audit(con, now, "POLICY_DECISION", **metadata, decision=effect)
                if effect == "DENY":
                    return response("DENY", "POLICY_DENIED", **metadata)
                if effect == "APPROVAL_REQUIRED":
                    expires = min(now + 300, session["expires_at"])
                    con.execute("INSERT INTO requests VALUES (?,?,?,?,?,'PENDING',?,NULL,?)",
                                (request_id, session_id, canonical(action), fingerprint,
                                 policy_hash, expires, now))
                    self.store.append_audit(con, now, "APPROVAL_PENDING", **metadata,
                                            pending_expires_at=expires)
                    return response(effect, effect, **metadata, pending_expires_at=expires)
                return self._execute(con, now, session, call, metadata)
        except AuthorityError as exc:
            return error_result(exc.code)
        except sqlite3.Error:
            return error_result("STORAGE_ERROR")

    def resume(self, session_id, request_id):
        from .contracts import evaluate
        try:
            identifier(session_id)
            identifier(request_id)
            policy = self._policy()
            with self.store.transaction() as con:
                now = self.clock()
                try:
                    session = self._session(con, session_id, now)
                    row = con.execute("SELECT * FROM requests WHERE id=? AND session_id=?",
                                      (request_id, session_id)).fetchone()
                    if row is None:
                        fail("REQUEST_UNAVAILABLE", "Request unavailable")
                    if row["state"] == "CONSUMED":
                        fail("APPROVAL_CONSUMED", "Approval already consumed")
                    if row["state"] in {"PENDING", "APPROVED"} and now >= row["pending_expires_at"]:
                        fail("APPROVAL_EXPIRED", "Pending action deadline expired")
                    if row["state"] == "PENDING":
                        fail("APPROVAL_REQUIRED", "Operator approval required")
                    if row["state"] != "APPROVED":
                        fail("APPROVAL_UNUSABLE", "Approval unavailable")
                    if now >= min(row["pending_expires_at"], row["grant_expires_at"]):
                        fail("APPROVAL_EXPIRED", "Approval expired")
                    action = parse_json(row["action_json"])
                    if digest(action) != row["fingerprint"] or action["session"] != session:
                        fail("ACTION_CHANGED", "Reviewed action changed")
                    if row["policy_digest"] != digest(policy):
                        fail("POLICY_CHANGED", "Policy changed since review")
                    call = validate_call(action["call"])
                    self._scope(con, session, call)
                    effect, rules = evaluate(policy, session, call)
                    if effect == "DENY":
                        fail("POLICY_DENIED", "Current policy denies the action")
                except AuthorityError as exc:
                    # A foreign request ID is not returned to the agent or placed in its result.
                    metadata = {"session_id": session_id, "code": exc.code}
                    if exc.code not in {"REQUEST_UNAVAILABLE", "SESSION_UNAVAILABLE"}:
                        metadata["request_id"] = request_id
                    if exc.code in {"ACTION_CHANGED", "POLICY_CHANGED", "STALE_RESOURCE",
                                    "APPROVAL_EXPIRED", "POLICY_DENIED"}:
                        con.execute("UPDATE requests SET state='FAILED' WHERE id=? AND session_id=?",
                                    (request_id, session_id))
                    self.store.append_audit(con, now, "RESUME_REJECTED", **metadata)
                    return error_result(exc.code)
                metadata = self._metadata(session, call, request_id, row["fingerprint"],
                                          row["policy_digest"], rules)
                return self._execute(con, now, session, call, metadata, consume=True)
        except AuthorityError as exc:
            return error_result(exc.code)
        except sqlite3.Error:
            return error_result("STORAGE_ERROR")

    def record_harness_failure(self, session_id, reason):
        """Trusted supervisor telemetry; not part of the agent facade/tool registry."""
        identifier(session_id)
        identifier(reason)
        try:
            with self.store.transaction() as con:
                self.store.append_audit(con, self.clock(), "HARNESS_FAILED",
                                        session_id=session_id, code="HARNESS_ERROR", reason=reason)
            return True
        except sqlite3.Error:
            return False  # No durable row is claimed when storage is unavailable.


class OperatorService:
    """Trusted host operator channel. Never attach this service to model tools."""

    def __init__(self, gateway):
        self.gateway = gateway

    @staticmethod
    def _review(row):
        action = parse_json(row["action_json"])
        return {"request_id": row["id"], "state": row["state"], "action": action,
                "fingerprint": row["fingerprint"], "policy_digest": row["policy_digest"],
                "pending_expires_at": row["pending_expires_at"],
                "grant_expires_at": row["grant_expires_at"]}

    def pending(self, request_id):
        try:
            identifier(request_id)
            with self.gateway.store.transaction() as con:
                row = con.execute("SELECT * FROM requests WHERE id=?", (request_id,)).fetchone()
                if row is None:
                    fail("REQUEST_UNAVAILABLE", "Request unavailable")
                return response("ALLOW", "REVIEW", review=self._review(row))
        except AuthorityError as exc:
            return error_result(exc.code)
        except sqlite3.Error:
            return error_result("STORAGE_ERROR")

    def approve(self, request_id, fingerprint, ttl_seconds=60):
        try:
            identifier(request_id)
            integer(ttl_seconds, maximum=60)
            policy_hash = digest(self.gateway._policy())
            with self.gateway.store.transaction() as con:
                now = self.gateway.clock()
                try:
                    row = con.execute("SELECT * FROM requests WHERE id=?", (request_id,)).fetchone()
                    if row is None:
                        fail("REQUEST_UNAVAILABLE", "Request unavailable")
                    if row["state"] != "PENDING":
                        fail("APPROVAL_UNUSABLE", "Only a pending request can be approved")
                    session = self.gateway._session(con, row["session_id"], now)
                    if now >= row["pending_expires_at"]:
                        fail("APPROVAL_EXPIRED", "Pending request expired")
                    if not isinstance(fingerprint, str) or fingerprint != row["fingerprint"]:
                        fail("FINGERPRINT_MISMATCH", "Review fingerprint differs")
                    if row["policy_digest"] != policy_hash:
                        fail("POLICY_CHANGED", "Policy changed since request")
                    action = parse_json(row["action_json"])
                    if digest(action) != row["fingerprint"] or action["session"] != session:
                        fail("ACTION_CHANGED", "Stored action changed")
                    self.gateway._scope(con, session, validate_call(action["call"]))
                    expires = min(now + ttl_seconds, row["pending_expires_at"], session["expires_at"])
                    con.execute("UPDATE requests SET state='APPROVED',grant_expires_at=? WHERE id=?",
                                (expires, request_id))
                    self.gateway.store.append_audit(con, now, "OPERATOR_APPROVED", request_id=request_id,
                                                    fingerprint=fingerprint, policy_digest=policy_hash,
                                                    actor_type="local_operator", actor_label=getpass.getuser(),
                                                    grant_expires_at=expires)
                    return response("ALLOW", "APPROVED", request_id=request_id,
                                    fingerprint=fingerprint, grant_expires_at=expires)
                except AuthorityError as exc:
                    if exc.code in {"ACTION_CHANGED", "POLICY_CHANGED", "STALE_RESOURCE", "APPROVAL_EXPIRED"}:
                        con.execute("UPDATE requests SET state='FAILED' WHERE id=? AND state='PENDING'",
                                    (request_id,))
                    self.gateway.store.append_audit(con, now, "APPROVAL_REJECTED", code=exc.code,
                                                    actor_type="local_operator")
                    return error_result(exc.code)
        except AuthorityError as exc:
            return error_result(exc.code)
        except sqlite3.Error:
            return error_result("STORAGE_ERROR")

    def reject(self, request_id, fingerprint):
        """Explicit operator decision on a reviewed pending action."""
        try:
            identifier(request_id)
            with self.gateway.store.transaction() as con:
                now = self.gateway.clock()
                try:
                    row = con.execute("SELECT * FROM requests WHERE id=?", (request_id,)).fetchone()
                    if row is None:
                        fail("REQUEST_UNAVAILABLE", "Request unavailable")
                    if row["state"] != "PENDING":
                        fail("APPROVAL_UNUSABLE", "Only pending requests can be rejected")
                    if not isinstance(fingerprint, str) or fingerprint != row["fingerprint"]:
                        fail("FINGERPRINT_MISMATCH", "Review fingerprint differs")
                    con.execute("UPDATE requests SET state='REJECTED' WHERE id=?", (request_id,))
                    self.gateway.store.append_audit(con, now, "OPERATOR_REJECTED", request_id=request_id,
                                                    fingerprint=fingerprint, actor_type="local_operator",
                                                    actor_label=getpass.getuser())
                    return response("ALLOW", "REJECTED", request_id=request_id)
                except AuthorityError as exc:
                    self.gateway.store.append_audit(con, now, "REJECTION_REFUSED", code=exc.code,
                                                    actor_type="local_operator")
                    return error_result(exc.code)
        except AuthorityError as exc:
            return error_result(exc.code)
        except sqlite3.Error:
            return error_result("STORAGE_ERROR")
