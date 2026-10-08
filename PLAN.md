# Agent Tool Authority: proposed MVP

Status: **planning complete; awaiting the main chat's accepted milestone assignment.**
Research retrieved: **2026-10-07**. No implementation, application tests, paid model calls, installation, publication, or deployment has occurred.

Repository: `C:/Users/shash/Documents/CodexPortfolios/agentic-ai-2026-10-07/agent-tool-authority`.
Worker record: `C:/Users/shash/Documents/CodexPortfolios/agentic-ai-2026-10-07/coordination/workers/agent-tool-authority`.

## 1. User problem and journey

A developer connecting an agent to a company tool needs an answer to: **may this agent perform this exact action on this resource now, and was the action actually executed?** Prompt instructions and a model-provided `approved: true` field do not enforce permissions. A broad approval such as “allow ticket updates” also permits a changed action after review.

Build a reusable Python enforcement gateway plus an operator CLI. Demonstrate it with a fictional support team's local ticket store. Agent requests are structured JSON; the gateway binds trusted session identity, validates arguments, evaluates policy, and alone dispatches the tool adapter. The operator reviews a pending action and approves its fingerprint; the agent can then resume that stored action once, before expiration.

Concrete quickstart journey, all offline:

1. Initialize a new workspace with two fictional tenants, a policy, a bounded agent session, and a SQLite ticket store.
2. Run a scripted mock agent which asks to read an authorized ticket: `ALLOW`, tool executes.
3. Ask to close the ticket: `DENY`, tool does not execute.
4. Ask to resolve the ticket: `APPROVAL_REQUIRED`, no mutation; display the exact ticket, status, expected resource version, session, policy digest, fingerprint, and deadline.
5. An operator explicitly approves that fingerprint using a separate CLI command. Resume executes the stored action, changes one local ticket version, consumes the grant, and records its outcome.
6. Repeating the resume is rejected. Inspect the ordered audit export and the final ticket state.

The demonstration is **scripted mock execution with real local gateway and SQLite tool execution**. It is neither fresh model execution nor recorded model replay. It needs no API key or network service.

The useful integration API is a restricted agent facade with `submit(call)` and `resume(request_id)`, and a separate trusted operator service. A small adapter contract demonstrates how an application author attaches typed local tools. No agent-facing interface exposes operator approval, policy installation, arbitrary code, shell execution, or database access.

## 2. Existing tools, overlap, and contribution

| Existing capability | Evidence read | Implication for this project |
| --- | --- | --- |
| OPA/Rego already handles policies on agent tool names and parameters, with a harness enforcing the decision and decision logging. | [OPA Agent Tool Calling](https://www.openpolicyagent.org/docs/agent-tool-calling) and [OPA FAQ](https://www.openpolicyagent.org/docs/faq) | Do not claim that external policy enforcement or agent permission gating is novel. Avoid adding an OPA server to this small MVP. |
| Cedar uses principal/action/resource/context requests, explicit permits, default deny, and forbid precedence. | [Cedar authorization](https://docs.cedarpolicy.com/auth/authorization.html) | Adopt familiar default-deny and deny-precedence principles; do not implement or claim Cedar compatibility. |
| LangGraph can persist an interrupted graph and resume it with external input; re-entered nodes need careful side-effect placement. | [LangGraph interrupts](https://docs.langchain.com/oss/python/langgraph/interrupts) | A framework approval pause is substantial overlap. This repository focuses on the execution gate, exact approved payload, expiration, and database commit boundary. No LangGraph dependency. |
| MCP tool guidance discusses human review and treats annotations as untrusted unless supplied by a trusted server. | [MCP tools, revision 2025-11-25](https://modelcontextprotocol.io/specification/2025-11-25/server/tools) | Model-supplied labels cannot confer permission. The MVP is not an MCP server/proxy and makes no MCP conformance claim. |
| OWASP recommends granular tools, minimum permissions, human approval for impactful actions, and authorization outside LLM decisions. | [OWASP LLM06:2025 Excessive Agency](https://genai.owasp.org/llmrisk/llm062025-excessive-agency/) | Motivate the threat boundary without claiming that passing this tool eliminates prompt injection or proves security. |

Original contribution **within this repository**, rather than a claim of ecosystem novelty: a dependency-free, inspectable reference integration joining finite scoped policies, immutable pending actions, short-lived single-use approvals, resource-version checks, and transactional local execution/audit. A reproducible misuse suite shows where enforcement takes place and what it refuses. Its value is the small reusable gateway and evidence, not a new policy language or enterprise IAM replacement.

## 3. Narrow scope and explicit non-goals

MVP:

- JSON policy schema `ata-policy/v1`: exact principal, tenant, project, tool name, finite ticket IDs, and optional finite target-status restrictions. All grant scopes must be explicit. No regex, wildcards, expression evaluation, or inheritance.
- Effects `ALLOW`, `DENY`, `APPROVAL_REQUIRED`; order-independent precedence **DENY > APPROVAL_REQUIRED > ALLOW**, otherwise default deny. All determining rule IDs appear in diagnostics. Invalid policy blocks execution instead of silently skipping rules.
- Trusted persisted sessions with exact principal/tenant/project binding and expiration. The agent payload cannot choose its identity or extend the deadline.
- Two typed tools: `tickets.read` and `tickets.set_status`. Mutations require `expected_version`; supported status values are `open`, `triaged`, `resolved`, and `closed`. Data and effects remain inside a local SQLite fixture workspace.
- Policy examples: scoped read and triage allowed, resolve requires approval, close explicitly denied. A second tenant and out-of-scope ticket provide denial cases.
- Pending action review, explicit approve/reject, expiration, resume, single-use consumption, audit export, and a scripted mock subprocess harness.
- Python API, CLI, meaningful failure tests, offline demonstration, architecture/threat-boundary documentation, MIT license, dependency attribution, and no-paid-call CI.

Non-goals: real SaaS/account tools, HTTP service, web dashboard, OAuth/SSO/RBAC product, MCP/A2A implementation, arbitrary filesystem or shell tools, model/provider SDK, policy synthesis, distributed grants, approval notifications, cryptographically protected audit, OS sandbox, hostile plugin execution, or external exactly-once side effects. No live-model evaluation or performance benchmark is required.

## 4. Architecture and trust boundary

```text
scripted mock subprocess / future model output
    JSONL calls only; untrusted tool names and arguments
                 |
                 v
trusted supervisor: bound Session -> AgentFacade -> Gateway
                                            |          |
                                      PolicyEngine  ApprovalStore
                                            |          |
                                            +----+-----+
                                                 |
                                  trusted typed adapter registry
                                                 |
                            SQLite transaction: tickets + grants + audit

local operator CLI -> separate OperatorService -> approve/reject
```

The supervisor constructs session identity from trusted configuration; the worker supplies only a tool call or a pending-action ID. The agent does not receive an approval tool. An attempted `authority.approve` tool, forged identity field, or `approved: true` field is rejected before dispatch. Tool descriptions and model conclusions are never authorization inputs.

This is a **host-side mediation boundary for model-generated requests**. The trusted application must route every protected call through the gateway and keep operator capabilities and tool credentials away from the model's tool surface. A Python subprocess running under the same Windows user is not an OS security boundary: malicious executable code or a host owner can inspect/edit files, import trusted code, or bypass the gateway. The demo worker is supplied trusted scripted code producing untrusted requests; it is not a sandbox for arbitrary code.

Proposed small modules: `models`, `validation`, `policy`, `store`, `gateway`, `tools`, `cli`, and `mock_agent`; standard-library `unittest` tests and JSON examples. The Python API separates the restricted agent facade from the trusted administrative service. Database/policy paths are operator configuration, never request arguments. CLI operator identity is a locally recorded OS user label, not authenticated enterprise identity.

### Approval lifecycle

1. Strictly validate and normalize a request. Reject duplicate JSON keys, unknown fields, invalid types (including booleans used as integer versions), unsupported schema versions, non-finite numbers, oversized frames, and missing scopes. Tool arguments contain only bounded identifiers, enums, and integer versions.
2. Load resource tenant/project and version from the store; do not rely on a request's description of the resource. Evaluate a validated immutable policy snapshot. Session expiry and resource scope are hard checks before policy.
3. `DENY`: persist a decision with no tool invocation. `ALLOW`: execute the adapter through the transaction boundary. `APPROVAL_REQUIRED`: persist an immutable normalized action and pending record with no mutation.
4. Fingerprint the internal normalized action using a documented SHA-256 encoding: fixed JSON fields, UTF-8, sorted keys, compact separators, no floats. Bind schema version, session ID, principal, tenant, project, tool, all arguments including expected resource version, and policy digest. This is a comparison identifier, not a signature or bearer credential.
5. Operator `approve` requires both request ID and the reviewed fingerprint. The approval is single-use and its deadline is the minimum of pending-request deadline, session deadline, and operator-selected TTL (positive, at most 60 seconds by default). Pending deadline defaults to 300 seconds. Approval never changes tool parameters or widens policy. Operator may also reject a pending request.
6. `resume(request_id)` accepts no replacement arguments. Verify the same bound session, exact policy digest, approval state, and trusted current time; then re-evaluate policy and resource version immediately before mutation. A policy change invalidates the old request even if the new policy is looser. A stale ticket version requires a new request and review.
7. Consume the approval, apply the local ticket update, and record execution outcome in **one SQLite transaction**. A concurrent second resume cannot commit another update. Successful commits persist across reopening the store.

States: `PENDING -> APPROVED -> CONSUMED`, or `REJECTED`; time-derived expiry makes pending/approved requests unusable. Stale-version, policy-change, and adapter-failure outcomes become terminal failures requiring a fresh request. Unknown or wrong-session request IDs return a generic unavailable result to avoid disclosing another session's payload.

### Reliability and audit semantics

Use explicit SQLite transactions (`isolation_level=None`, `BEGIN IMMEDIATE`, explicit commit/rollback), parameterized SQL, foreign keys, and a bounded busy timeout. A validated policy snapshot applies to a single call; snapshot acquisition is the policy decision boundary. Already executing operations are not retroactively revoked.

For adapter failure, a savepoint allows rollback of any local ticket changes while committing a terminal failed approval/outcome, when the store remains writable. Storage/audit failure prevents mutation from committing. If the database is unavailable, report `STORAGE_ERROR` without claiming a durable audit event. Process termination before commit leaves no partial local update; termination after commit may lose the response but a repeated resume cannot apply the action again. Document this as transactional behavior of the local example, not an exactly-once guarantee for external APIs.

Audit rows have monotonic sequence IDs, UTC timestamps, request/session correlation, principal/tenant/project, tool/resource identifiers, policy/rule IDs, decision/reason codes, action fingerprint, approval transitions, and execution result/version. Use safe summaries rather than arbitrary argument bodies, tool output, or stack traces. Export stable JSONL via the supported read-only CLI. The supported API appends records; a database owner can alter them, so the audit is not tamper-proof, signed, or an immutable compliance archive. Pending-action storage is also a trusted local file store, not encrypted storage.

### Language and pinned dependencies

Python is justified by an embeddable agent-facing API, strict JSON handling, subprocess harnessing, and built-in SQLite transactions. A Java service or Maven wrapper would add tooling and dependencies without improving this local reference boundary. Use only the Python standard library at runtime and for tests: `argparse`, `dataclasses`, `json`, `hashlib`, `sqlite3`, `subprocess`, `threading`, `queue`, `time`, `datetime`, `secrets`, `pathlib`, and `unittest`. No pip packages, services, containers, or machine-wide installation.

| Component | Exact baseline / pin | Artifact and license evidence |
| --- | --- | --- |
| Local Python baseline | CPython **3.11.9**, invoked as `py -3.11`; `.python-version` will state `3.11.9`. | Installed and actually probed. [Official release](https://www.python.org/downloads/release/python-3119/) lists source and Windows x64 artifacts. [Version-specific license](https://raw.githubusercontent.com/python/cpython/v3.11.9/LICENSE): PSF License Version 2 and incorporated notices. No interpreter redistribution. |
| Local SQLite baseline | **3.45.1**, bundled in the probed Python 3.11.9 runtime. | Installed and importable, not separately downloaded. [Release](https://www.sqlite.org/releaselog/3_45_1.html); [copyright](https://www.sqlite.org/copyright.html) dedicates the deliverable library to the public domain. Runtime SQLite can vary by distribution; evidence prints its actual version rather than asserting an identical CI bundle. |
| Alternate observed runtime | PATH `python`: **3.12.7**, bundled SQLite **3.45.3**. | Installed and actually probed. [Official release](https://www.python.org/downloads/release/python-3127/). Supplemental compatibility check only; `python` is not assumed to select the baseline on this HP. |
| Application formats | `ata-policy/v1`, `ata-call/v1`, `ata-audit/v1`, SQLite schema version **1**. | Project-owned bounded contracts to be documented. Not JSON Schema validation, JSON-RPC, MCP, or Cedar compatibility. |
| Runtime/test third-party packages | **None**. | No resolver, requirements installation, or downloaded dependencies required for quickstart. |
| CI checkout | `actions/checkout` **v7.0.1**, commit `3d3c42e5aac5ba805825da76410c181273ba90b1`. | Actual `git ls-remote` result; [action source](https://raw.githubusercontent.com/actions/checkout/v7.0.1/action.yml) has Node 24 runtime; [MIT license](https://raw.githubusercontent.com/actions/checkout/v7.0.1/LICENSE). CI use only, not runtime code. |
| CI Python setup | `actions/setup-python` **v7.0.0**, commit `5fda3b95a4ea91299a34e894583c3862153e4b97`. | Actual `git ls-remote` result; [action source](https://raw.githubusercontent.com/actions/setup-python/v7.0.0/action.yml) has Node 24 runtime; [MIT license](https://raw.githubusercontent.com/actions/setup-python/v7.0.0/LICENSE). |
| CI interpreter artifacts | CPython **3.11.9**, x64, proposed `ubuntu-24.04` and `windows-2025`. | [Official Actions manifest](https://raw.githubusercontent.com/actions/python-versions/main/versions-manifest.json) actually read: release `3.11.9-9947079978` lists Linux 24.04 x64 and Windows x64 packages. Manifest listing establishes availability, not downloaded binary verification or an executed CI job. |

The fixed older runtime is a reproducibility baseline already on the user's machine, not a claim that it is the latest patch. The Python 3.11 online documentation read resolves to 3.11.17; implementation uses the stable 3.11 transaction API, not new patch-only features. No upstream engine or framework code will be vendored. New repository code, docs, and self-authored fictional fixtures use MIT; `THIRD_PARTY_NOTICES.md` records runtime/CI attribution and distinguishes research-only references.

## 5. Bounded milestones and required deliverables

**M1: first runnable end-to-end slice (the recommended next assignment).** Implement strict finite policy evaluation, trusted sessions, two local ticket adapters, SQLite state, pending/approve/resume and audit export, CLI entry point, and scripted mock subprocess supervisor. One command demonstrates read allowed, close denied, resolve pending, explicit simulated operator approval, and successful resume with before/after state. Include basic tests proving denied and pending calls have no mutation, no agent approval capability, and approved execution changes one version. Deliver the minimal quickstart, limitations paragraph, MIT license, and actual command evidence. Do not add providers or protocol SDKs.

**M2: required failure behavior and bounded reliability.** Add expiry boundaries via a trusted injectable clock, rejected approvals, wrong fingerprints/session, changed policy, stale resource, consumed-grant replay, duplicate-key/malformed/oversized input, and overlapping-rule precedence. Test transactional adapter rollback, audit/storage failure, concurrent same-grant resume, store reopening, and one controlled process termination around the local commit. Bound mock subprocess duration, frame size, and call count; terminate a hung worker and record failure. Implement this milestone only after the main chat assigns it. No broad fuzz campaign or heavyweight integration environment.

**M3: review package and CI.** Complete `README.md`, `docs/architecture.md`, `docs/contracts.md`, `docs/threat-model.md`, `docs/original-contribution.md`, `THIRD_PARTY_NOTICES.md`, example requests/policy/mock script, no-paid-call Actions workflow, and `EVIDENCE.md`. Verify the documented manual operator journey in addition to the automatic mock demo. Print actual interpreter/SQLite versions, commands, exit codes, observed counts/state and explicitly unexecuted checks. CI uses pinned actions, `permissions: contents: read`, no paid calls or secrets, and tests/demo on Windows and Linux. This local phase cannot produce a hosted CI result; label it unexecuted until run after separately authorized publication.

Each milestone stops with its own status/evidence and awaits the main chat's next bounded instruction. Planning/ordinary bounded unit checks need no heavy lease. Any later large install, heavyweight integration suite, or build requires a named main-granted lease in `coordination/resources.json`; workers cannot write that file.

## 6. Acceptance commands and concrete assertions

These are **planned commands, not claims of execution**. Run from this repository. On the HP use `py -3.11`; elsewhere use the explicit baseline interpreter.

```powershell
py -3.11 -m agent_tool_authority --help
py -3.11 -m agent_tool_authority demo --workspace work/demo --json
py -3.11 -m unittest discover -s tests -v
py -3.11 -m agent_tool_authority audit --workspace work/demo --format jsonl
```

- Help succeeds and explains the mock/local execution mode and operator commands.
- Demo exits `0` only when its assertions pass and emits a structured summary with `mode = scripted_mock`, `paid_model_calls = 0`, read result `ALLOW/EXECUTED`, close result `DENY/NOT_EXECUTED`, initial resolve result `APPROVAL_REQUIRED/NOT_EXECUTED`, and approved resume `EXECUTED`. Denied and pending attempts do not change ticket version; approved resume increments it once. Replaying the consumed approval produces `APPROVAL_CONSUMED` and no further version change.
- Demo initializes only a new/empty workspace; repeating against a populated path fails safely and tells the user to choose a fresh directory. It does not silently erase a prior run.
- CLI exit-code contract: `0` success, `2` invalid configuration/input or operational failure, `3` pending approval, `4` denied/unusable authorization. The automatic demo handles expected denials itself and returns `0` if their assertions pass.
- Audit JSONL contains `ata-audit/v1` rows in increasing sequence order linking the request decision, operator approval and committed execution. It contains no grant bearer token, secret, arbitrary tool output, or model-provided approval assertion.
- Unit test suite exits `0`, with semantic assertions on actual tool invocation counters, database versions, grant state, and audit state, not only policy return strings.

Manual approval path (request ID and fingerprint come from real preceding output):

```powershell
py -3.11 -m agent_tool_authority init --workspace work/manual
py -3.11 -m agent_tool_authority submit --workspace work/manual --session support-agent --request examples/requests/read.json
py -3.11 -m agent_tool_authority submit --workspace work/manual --session support-agent --request examples/requests/resolve.json
py -3.11 -m agent_tool_authority pending --workspace work/manual --request-id <request-id>
py -3.11 -m agent_tool_authority approve --workspace work/manual --request-id <request-id> --fingerprint <reviewed-fingerprint> --ttl-seconds 60
py -3.11 -m agent_tool_authority resume --workspace work/manual --session support-agent --request-id <request-id>
```

The final two commands succeed only before the pending/session/grant deadlines. README will provide usable PowerShell instructions to copy the emitted values; placeholders must not be presented as runnable literal arguments.

| Failure test | Required observation |
| --- | --- |
| Default deny, explicit deny overlap, approval/allow overlap | No adapter dispatch for denied/pending calls; precedence is invariant under rule ordering. |
| Cross-tenant/project/resource; unknown tool; forged identity/approval fields | Refusal before dispatch; the agent cannot obtain another scope or use operator capabilities. |
| Malformed policy/call, duplicate keys, unknown schema, oversized JSONL | Bounded typed error; no tool execution. Policy failure never falls back to allow. |
| Expired session/pending/grant, exact deadline | At `now >= expires_at`, unusable; tests use a trusted fake clock without sleeps or agent-supplied time. |
| Wrong fingerprint, changed policy, stale resource version | Approval/resume fails; ticket remains unchanged and a fresh request is required. |
| Rejected or consumed approval; wrong session; replacement resume args | No execution. Foreign request payload is not disclosed. |
| Two connections racing the same approved action | Exactly one committed local ticket version increment and one consumed grant; losing call reports unusable approval. This is a local transaction assertion only. |
| Adapter mutates then raises; audit write fails | Ticket mutation rolls back. A writable store records terminal tool failure; an unwritable store reports storage failure without falsely claiming an audit row. |
| Reopen/restart; controlled termination before/after commit | Pending/approval survives reopening; no partial local state; post-commit replay cannot apply the action again. No power-loss guarantee inferred from these tests. |
| Mock worker hangs/emits invalid or too many frames | Supervisor bounds duration/size/count, cleans up the worker, reports harness error, and does not dispatch invalid calls. |

## 7. Material risks, resolved choices, and planning evidence

- **Bypass by an application or same-user process:** the gateway only protects calls routed through it. Document trust assumptions prominently; no arbitrary code runner or shell tool is present.
- **Identity/authentication:** session identities come from trusted configuration. The local operator channel trusts the host user. An enterprise integration must provide authenticated operator identity and separate permissions; that integration is out of scope.
- **Policy/action drift:** approvals bind exact normalized payload and policy digest, and mutation requires the reviewed resource version. Policy reloads affect later snapshot acquisitions; no immediate revocation claim for calls already executing.
- **Clock correctness:** persisted expiry uses authority UTC time. Fake time exists only in trusted tests/demo internals. Clock rollback or an incorrect host clock is outside the local guarantee; not a distributed lease service.
- **Audit durability/privacy:** API append-only is not cryptographic immutability; storage errors can prevent durable denial logs. Bounded fictional arguments avoid sensitive content. Future adapters need their own data-retention/redaction design.
- **External tools:** the SQLite commit property does not carry over to HTTP APIs. Such adapters need separate idempotency/uncertain-outcome handling and are deliberately excluded.
- **Cross-platform harness:** Windows pipe timeouts require a bounded reader/queue and explicit process cleanup. Test locally on the observed HP; Linux hosted CI remains unexecuted here.

Routine decisions resolved: Python only, no external package dependency, two typed local tools, finite exact scope matching, short-lived session/approval capability, SQLite transaction, SHA-256 comparison fingerprint, mock subprocess, MIT license, and no network connector. **No essential human question or technical blocker remains.** The next required action is the main chat's plan review and explicit M1 assignment.

Actual planning checks: read repository `AGENTS.md`, own assignment/status, full human authorization and read-only resource policy; `rg --files --hidden -g '!\\.git/**'` found only `AGENTS.md`; `git status --short --branch` reported no commits and untracked `AGENTS.md`; `python --version` reported 3.12.7; `Get-Command python,py`/`py -0p` identified local interpreters; `py -3.11` runtime probe reported Python 3.11.9 and SQLite 3.45.1; PATH runtime probe reported Python 3.12.7 and SQLite 3.45.3. Both CI tag lookups succeeded with the full commit IDs above. Primary sources in this document were actually opened, not only obtained from search snippets. Artifact availability above means official release/manifest listing plus the local imports where stated; no binaries were downloaded or signature-checked.

Unexecuted: implementation, CLI quickstart, demo, unit/failure tests, process/concurrency tests, CI, live model calls, performance/security benchmarking. No result from these is claimed. Research docs and tag refs were small read-only operations; no heavy lease was used.
