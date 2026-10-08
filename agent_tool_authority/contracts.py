"""Small project-owned contracts. Not a general policy language or MCP."""

import hashlib
import json
import math
import re

MAX_FRAME = 16_384
STATUSES = frozenset({"open", "triaged", "resolved", "closed"})
TOOLS = frozenset({"tickets.read", "tickets.set_status"})


class AuthorityError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def fail(code, message):
    raise AuthorityError(code, message)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                      allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def _object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            fail("INVALID_INPUT", "Duplicate JSON keys are not accepted")
        value[key] = item
    return value


def _finite_float(raw):
    value = float(raw)
    if not math.isfinite(value):
        fail("INVALID_INPUT", "Non-finite JSON value")
    return value


def parse_json(raw, maximum=MAX_FRAME):
    if not isinstance(raw, str):
        fail("INVALID_INPUT", "JSON input must be UTF-8 text")
    try:
        size = len(raw.encode("utf-8"))
    except UnicodeError as exc:
        raise AuthorityError("INVALID_INPUT", "Invalid UTF-8 text") from exc
    if size > maximum:
        fail("INVALID_INPUT", "JSON input exceeds the supported size")
    try:
        return json.loads(raw, object_pairs_hook=_object, parse_float=_finite_float,
                          parse_constant=lambda _: fail("INVALID_INPUT", "Non-finite JSON value"))
    except (ValueError, TypeError, RecursionError) as exc:
        raise AuthorityError("INVALID_INPUT", "Invalid JSON input") from exc


def fields(value, required, optional=()):
    if not isinstance(value, dict) or not set(required) <= value.keys():
        fail("INVALID_INPUT", "Missing required object fields")
    if value.keys() - set(required) - set(optional):
        fail("INVALID_INPUT", "Unknown object fields are not accepted")


def identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}", value):
        fail("INVALID_INPUT", "Identifiers must be bounded ASCII names")
    return value


def integer(value, minimum=1, maximum=2**31 - 1):
    if type(value) is not int or not minimum <= value <= maximum:
        fail("INVALID_INPUT", "Integer outside the supported range")
    return value


def names(value):
    if not isinstance(value, list) or not 1 <= len(value) <= 32:
        fail("INVALID_INPUT", "Scope lists must contain 1 to 32 exact names")
    result = [identifier(item) for item in value]
    if len(result) != len(set(result)):
        fail("INVALID_INPUT", "Duplicate scope names")
    return result


def validate_call(value):
    fields(value, {"schema", "tool", "arguments"})
    if value["schema"] != "ata-call/v1":
        fail("INVALID_INPUT", "Unsupported call schema")
    if not isinstance(value["tool"], str) or value["tool"] not in TOOLS:
        fail("UNKNOWN_TOOL", "Tool is not in the trusted registry")
    args = value["arguments"]
    required = {"project", "ticket_id"}
    if value["tool"] == "tickets.set_status":
        required |= {"status", "expected_version"}
    fields(args, required)
    identifier(args["project"])
    identifier(args["ticket_id"])
    if value["tool"] == "tickets.set_status":
        if not isinstance(args["status"], str) or args["status"] not in STATUSES:
            fail("INVALID_INPUT", "Unsupported ticket status")
        integer(args["expected_version"])
    # Copy after validation; later caller edits cannot change a pending action.
    return parse_json(canonical(value))


def validate_policy(value):
    fields(value, {"schema", "rules"})
    if value["schema"] != "ata-policy/v1":
        fail("INVALID_INPUT", "Unsupported policy schema")
    if not isinstance(value["rules"], list) or len(value["rules"]) > 64:
        fail("INVALID_INPUT", "Policy supports at most 64 finite rules")
    seen = set()
    for rule in value["rules"]:
        fields(rule, {"id", "effect", "principals", "tenant", "project", "tool", "ticket_ids"},
               {"statuses"})
        rule_id = identifier(rule["id"])
        if rule_id in seen:
            fail("INVALID_INPUT", "Duplicate policy rule ID")
        seen.add(rule_id)
        if not isinstance(rule["effect"], str) or rule["effect"] not in {"ALLOW", "DENY", "APPROVAL_REQUIRED"}:
            fail("INVALID_INPUT", "Unsupported policy effect")
        names(rule["principals"])
        names(rule["ticket_ids"])
        identifier(rule["tenant"])
        identifier(rule["project"])
        if not isinstance(rule["tool"], str) or rule["tool"] not in TOOLS:
            fail("INVALID_INPUT", "Policy references an unknown tool")
        if "statuses" in rule:
            names(rule["statuses"])
            if rule["tool"] != "tickets.set_status" or set(rule["statuses"]) - STATUSES:
                fail("INVALID_INPUT", "Invalid status restriction")
    return parse_json(canonical(value), maximum=65_536)


def validate_session(value):
    fields(value, {"id", "principal", "tenant", "project", "expires_at"})
    for key in ("id", "principal", "tenant", "project"):
        identifier(value[key])
    integer(value["expires_at"], maximum=2**63 - 1)
    return dict(value)


def evaluate(policy, session, call):
    args = call["arguments"]
    matches = []
    for rule in policy["rules"]:
        if (session["principal"] in rule["principals"]
                and session["tenant"] == rule["tenant"]
                and session["project"] == rule["project"] == args["project"]
                and call["tool"] == rule["tool"]
                and args["ticket_id"] in rule["ticket_ids"]
                and ("statuses" not in rule or args.get("status") in rule["statuses"])):
            matches.append(rule)
    for effect in ("DENY", "APPROVAL_REQUIRED", "ALLOW"):
        if any(rule["effect"] == effect for rule in matches):
            return effect, sorted(rule["id"] for rule in matches if rule["effect"] == effect)
    return "DENY", []
