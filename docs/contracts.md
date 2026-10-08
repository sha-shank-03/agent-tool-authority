# Supported contracts

All formats are project owned version 1, unrelated to MCP/OPA/Cedar wire or policy formats. No migration or backward-compatibility layer is implemented. Runtime module version is 0.1.0; SQLite `user_version` is 1.

## Input and policy

JSON parsing rejects duplicate keys, invalid UTF-8/lone surrogates, malformed JSON, NaN/Infinity and floating overflow. Calls are at most 16,384 UTF-8 bytes; policy is at most 65,536 bytes. Unknown object fields are rejected. Identifiers match ASCII `[A-Za-z0-9][A-Za-z0-9_.-]{0,63}`. Integer fields require `type(value) is int`, excluding booleans and floats.

Call shape:

```json
{"schema":"ata-call/v1","tool":"tickets.set_status","arguments":{"project":"support","ticket_id":"T-100","status":"resolved","expected_version":1}}
```

| Tool | Exact argument fields | Output fields |
| --- | --- | --- |
| `tickets.read` | `project`, `ticket_id` | `id`, `project`, `status`, `version` |
| `tickets.set_status` | `project`, `ticket_id`, `status`, `expected_version` | Same fields after local update. |

Status is one of open, triaged, resolved, closed. Expected version is 1 through 2^31−1. There is no tenant/principal/approved/token/workspace argument; identity comes from the host-bound persisted session. Unknown tools fail as UNKNOWN_TOOL before dispatch. Actual resource lookup includes tenant/project/id. A successful mutation increments the version once, including when setting the current status.

Policy root has exactly `schema: ata-policy/v1` and `rules`, a list of zero to 64 rules. Each rule requires `id`, `effect`, `principals`, `tenant`, `project`, `tool`, `ticket_ids`; only `statuses` is optional. IDs are unique. Principal/ticket scopes contain 1–32 unique exact names; statuses are finite valid values and permitted only for tickets.set_status. There are no wildcard, regex, hierarchy, expression or group semantics. Empty policy denies all calls. Matching effects have precedence DENY > APPROVAL_REQUIRED > ALLOW; no matches means DENY. `rule_ids` contains only the rules determining the winning effect.

`init` creates support-agent bound to support-agent/acme-lab/support, expiring at host UTC time plus 1800 seconds. Fixture policy allows T-100 read and triage, requires approval to resolve and denies close. T-200 and the other-lab T-100 are not authorized by that policy.

## Stored action and approval state

An `ata-action/v1` object contains exactly `schema`, `session`, `call`, `policy_digest`. Session contains `id`, `principal`, `tenant`, `project`, `expires_at`; expiry is an integer 1 through 2^63−1. The validated call is copied before storage. Canonical JSON sorts object keys, preserves list order, uses compact separators, `ensure_ascii=False`, no non-finite numbers and UTF-8 encoding. Policy/action identifiers are lowercase SHA-256 hex digests of that encoding. The fingerprint is a comparison identifier, not a signature or bearer credential.

Pending ID is a random 24-character hex identifier. Pending deadline is `min(now + 300, session.expires_at)`; approved grant deadline is `min(now + ttl, pending_expires_at, session.expires_at)` with TTL 1–60 seconds (default 60). Expiration is inclusive: `now >= deadline` fails.

| Current state | Supported operation and result |
| --- | --- |
| PENDING | Exact review + valid approve -> APPROVED; exact reject -> REJECTED; resume before expiry -> APPROVAL_REQUIRED. |
| APPROVED | Valid resume commits local effect -> CONSUMED; approve/reject refused. |
| CONSUMED | Resume -> APPROVAL_CONSUMED; no additional dispatch. |
| REJECTED or FAILED | Resume/approve -> APPROVAL_UNUSABLE; no dispatch. |

Detected pending/action/policy/resource drift or expiry can set FAILED on approval/resume. A wrong review fingerprint leaves PENDING. Session expiry refuses permission; not every refusal changes stored state. Policy parse failures refuse old approvals without inventing a terminal transition. Review can inspect any stored state; it does not mean the grant is currently usable.

## Results, CLI and audit

Normal responses use `ata-result/v1` with `decision`, `code`, `execution`. Decisions are ALLOW, DENY, ERROR, APPROVAL_REQUIRED. Execution is EXECUTED only after successful local adapter effect/audit; otherwise NOT_EXECUTED. Optional successful metadata includes request/session/principal/tenant/project/tool/ticket IDs, fingerprint, policy digest, winning rule IDs, output or operator review. Error codes omit arbitrary exception text, raw bodies and foreign-request data. `init` uses a simpler fixture result, `demo` an assertion summary, and `audit` JSONL rather than this response envelope.

| CLI command | Required flags beyond `--workspace` |
| --- | --- |
| init, demo | None; demo accepts `--json`. |
| submit | `--session`, `--request` (UTF-8 call JSON file). |
| pending | `--request-id`. |
| approve | `--request-id`, `--fingerprint`; optional `--ttl-seconds`. |
| reject | `--request-id`, `--fingerprint`. |
| resume | `--session`, `--request-id`. |
| audit | Optional `--format jsonl`, the only supported format. |

Native CLI statuses: 0 ALLOW/successful demo/export; 2 input/config/storage/harness error; 3 awaiting approval; 4 denied/unusable authorization. Argparse also exits 2 for syntax errors. Expected negative statuses must be asserted explicitly by automation. INVALID_INPUT/POLICY_ERROR/STORAGE_ERROR are operational errors; SCOPE_DENIED/UNKNOWN_TOOL/STALE_RESOURCE/APPROVAL_CONSUMED/APPROVAL_UNUSABLE are denials. No error indicates permission to retry without the checks.

Audit rows use `ata-audit/v1`, increasing `sequence`, integer UTC Unix seconds `timestamp`, `event` and safe event-specific metadata. Events include WORKSPACE_INITIALIZED, CALL_REJECTED, POLICY_DECISION, APPROVAL_PENDING, OPERATOR_APPROVED, OPERATOR_REJECTED, APPROVAL_REJECTED, REJECTION_REFUSED, RESUME_REJECTED, TOOL_EXECUTED, TOOL_FAILED, EXECUTION_REJECTED and HARNESS_FAILED. Audit includes identifying scope, decision/code, matching rules, digests, transitions/deadlines and successful version where relevant. Arbitrary raw arguments, tool output and tracebacks are excluded. Operator OS username is a label, not authentication. The API appends audit; the database owner can change it. Invalid input-file/policy parsing or unavailable storage can prevent durable audit, so there is no every-attempt logging guarantee.
