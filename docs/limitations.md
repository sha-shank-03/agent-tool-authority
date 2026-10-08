# Threat model and limitations

This library protects the supported tool path against untrusted model call data. It assumes a trusted host binds session identity, keeps operator methods separate, selects the workspace and mediates every protected action. Policy/database ownership, host clock, Python process, local operator channel and adapter implementation are trusted.

| Attempt or fault | Enforced behavior | Practical limit |
| --- | --- | --- |
| Forge identity/approval fields or request an approval tool | Strict exact call fields and fixed registry refuse dispatch. | Host can bypass the facade; Python private attributes are not access control against arbitrary code. |
| Access another project/ticket/tenant | Host-bound scope plus actual compound-key resource lookup and finite rules. | No tenant authentication, delegated identity or enterprise account management is implemented. |
| Replace an approved call, change policy/session or reuse a stale version | Stored copied action/digest and current session/policy/version rechecks. | Policy snapshot acquisition is the decision boundary; later edits do not cancel an executing call. |
| Replay/race one grant | Local SQLite serialization and consumed state prevent another committed update. | After a rollback an adapter invocation may repeat; external effects have no exactly-once guarantee. |
| Expired request/grant | Time checks after lock acquisition and just before dispatch, with capped deadlines. | Trusts host UTC clock; cannot interrupt a running adapter or correct clock rollback. |
| Adapter/audit/store failure | Local rollback, safe result; writable storage can record a safe failure. | Some failures have no durable audit; arbitrary external side effects cannot be rolled back here. |
| Bad/stalled mock worker | Bounded frames/calls/exchange, direct-child kill/reap and thread joins. | Same-user subprocess is not an OS sandbox; descendants, arbitrary code, hardware stalls and hostile resource exhaustion are uncontained. |

The scripted mock and fault workers are self-authored controlled fixtures. Passing them says nothing about a live model's tool-selection quality or resistance to prompt injection. The project does not claim to detect prompt injection; it rejects actions beyond the supported authority contract regardless of model text. There is no live/recorded model evaluation.

Audit is inspectable and append-only through the supported API, not cryptographically sealed. The host/database owner can edit state, fingerprints, grants or logs and can call adapters directly. Fingerprints are unkeyed comparison IDs. OS username in an operator event is not a verified identity. Request files, policy and database have no automatic encryption or filesystem permission hardening.

Supported effects are local SQLite operations only. There is no network/shell tool, MCP server, remote connector, OAuth/enterprise approval service, distributed lease, policy expression language, package installation or secret store. Controlled termination tests distinguish before/after local commit; they do not simulate power loss or establish general filesystem durability. No security audit, performance benchmark or availability SLA has been performed.

Hosted Windows/Linux CI and POSIX command execution remain unobserved. CI pins actions/interpreter but not an immutable hosted runner image or identical SQLite build. Actual platform/runtime versions are recorded when the verifier runs. Consult EVIDENCE.md for which checks were executed and by whom; worker verification is separate from main's independent acceptance.
