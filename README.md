# Agent Tool Authority

[![CI](https://github.com/sha-shank-03/agent-tool-authority/actions/workflows/ci.yml/badge.svg)](https://github.com/sha-shank-03/agent-tool-authority/actions/workflows/ci.yml)

Open-source MIT project. [Project context](docs/PROJECT_CONTEXT.md) · [Independent local verification](docs/INDEPENDENT_VERIFICATION.md) · [Contributing](CONTRIBUTING.md)

A small Python gateway for scoped agent tool calls, explicit operator approvals, expiration and local audit. The host binds identity and enforces policy before two typed SQLite ticket tools can run. It allows an assigned read, denies closing the ticket, and holds resolution for review. Approved resume rechecks the exact action and commits the ticket update, grant consumption and execution audit together; replay is refused.

The example agent is a **scripted mock** making fresh requests to real local SQLite tools. It uses no live model, recorded model replay, API key, network service, pip package or paid call. The operator in the demo is an explicit trusted local simulation. All fixture tenants and tickets are fictional.

## Windows quickstart

Run from this repository with **CPython 3.11.9** installed. The verified local selector is `py -3.11`; `.python-version` records the baseline but does not select an interpreter by itself. PATH `python` on the development machine selects 3.12.7, which has not had a compatibility suite run.

```powershell
py -3.11 -c "import sys; assert sys.version_info[:3] == (3,11,9); print(sys.executable)"
if ($LASTEXITCODE -ne 0) { throw 'Python 3.11.9 is required.' }
$demoWorkspace = Join-Path 'work' ('demo-' + [guid]::NewGuid().ToString('N'))
py -3.11 -m agent_tool_authority demo --workspace $demoWorkspace --json
if ($LASTEXITCODE -ne 0) { throw 'Demo failed.' }
py -3.11 -m agent_tool_authority audit --workspace $demoWorkspace --format jsonl
if ($LASTEXITCODE -ne 0) { throw 'Audit export failed.' }
```

Use a fresh workspace path for every demo. `init`/`demo` refuse populated directories with native exit 2 and preserve the existing store. The files are `policy.json` and `authority.sqlite3`. SQLite is supplied by the interpreter; locally it is 3.45.1, and verification records the actual version on each platform.

Successful demo JSON contains `assertions: passed`, `mode: scripted_mock`, `model_execution: none`, `recorded_replay: false`, `paid_model_calls: 0` and `tools: real_local_sqlite`. It observes open/version 1 before approval, resolved/version 2 after resume, `APPROVAL_CONSUMED` on replay, exactly one read and one status adapter invocation, and nine audit records.

Run the complete bounded offline review check:

```powershell
py -3.11 scripts/verify_repository.py
if ($LASTEXITCODE -ne 0) { throw 'Verification failed; inspect the printed receipt path.' }
```

This runs the meaningful 44-test suite, a fresh asserting mock demo, separate approval/rejection CLI processes, expected-negative exit gates, and direct read-only SQLite observations. It writes a unique `work/verification/<UTC-and-UUID>/receipt.json` plus raw output and archived process receipts. It checks source hashes before/after. Everything stays under ignored `work/`; it neither installs dependencies nor calls a model.

## POSIX quickstart

Prepared for an installed `python3.11` resolving to 3.11.9; **POSIX commands and hosted Linux CI have not been executed locally**. Run from the repository root:

```sh
set -eu
python3.11 -c 'import sys; assert sys.version_info[:3] == (3,11,9); print(sys.executable)'
demoWorkspace="work/demo-$(python3.11 -c 'import uuid; print(uuid.uuid4().hex)')"
python3.11 -m agent_tool_authority demo --workspace "$demoWorkspace" --json
python3.11 -m agent_tool_authority audit --workspace "$demoWorkspace" --format jsonl
python3.11 scripts/verify_repository.py
```

The prepared [CI workflow](.github/workflows/ci.yml) selects Python 3.11.9 on Windows 2025 and Ubuntu 24.04 and runs that same verifier. Action commits are immutable, token permission is `contents: read`, checkout does not retain credentials, and two jobs have five-minute limits. There are no paid model calls, package installs, custom secrets, publishing or deployment steps. This is prepared public-repository CI; hosted execution is unobserved. See [verification notes](docs/verification.md).

## Manual operator approval

The documented [PowerShell journey](scripts/manual_operator.ps1) invokes separate native CLI processes with the actual request ID and stored fingerprint. It prints and checks the exact action, explicitly approves it through the trusted operator CLI, immediately resumes, asserts replay refusal and exports audit. It is a scripted simulation of a local operator, not enterprise authentication or human-in-the-loop evaluation.

```powershell
& ./scripts/manual_operator.ps1
```

The corrected script was executed locally in **Windows PowerShell 5.1.26100.9444** and **PowerShell 7.6.5**, using native PowerShell shell invocation. Its fresh workspace contains `commands.json`, per-command stdout/stderr and `receipt.json`, including actual exits, interpreter, cwd and source hashes. Its native exits are init 0, read 0, denied close 4, pending resolve 3, review 0, approve 0, resume 0, replay 4, audit 0. PowerShell wrappers can report exit 1 for a failed native command; use `$LASTEXITCODE` or direct subprocess return codes. The verifier also runs a separate reject journey: REJECTED remains terminal, subsequent approve/resume exit 4, and all tickets remain open/version 1. [Verification notes](docs/verification.md) record the tested shell environment and preserved launcher-specific preflight failure.

A manual POSIX equivalent follows. It explicitly handles expected nonzero exits even under `set -e`. Review the printed action before the approval command, then resume within its 60-second grant. If review takes longer, create a new workspace/request.

```sh
set -eu
run_expected() {
  expected="$1"; shift
  actual=0
  "$@" || actual=$?
  [ "$actual" -eq "$expected" ] || { printf 'Expected exit %s; got %s\n' "$expected" "$actual" >&2; return 1; }
}
python3.11 -c 'import sys; assert sys.version_info[:3] == (3,11,9)'
manualWorkspace="work/manual-$(python3.11 -c 'import uuid; print(uuid.uuid4().hex)')"
run_expected 0 python3.11 -m agent_tool_authority init --workspace "$manualWorkspace"
run_expected 0 python3.11 -m agent_tool_authority submit --workspace "$manualWorkspace" --session support-agent --request examples/requests/read.json
run_expected 4 python3.11 -m agent_tool_authority submit --workspace "$manualWorkspace" --session support-agent --request examples/requests/close.json
run_expected 3 python3.11 -m agent_tool_authority submit --workspace "$manualWorkspace" --session support-agent --request examples/requests/resolve.json > "$manualWorkspace-pending.json"
requestId=$(python3.11 -c 'import json,sys; print(json.load(open(sys.argv[1]))["request_id"])' "$manualWorkspace-pending.json")
run_expected 0 python3.11 -m agent_tool_authority pending --workspace "$manualWorkspace" --request-id "$requestId" > "$manualWorkspace-review.json"
cat "$manualWorkspace-review.json"
fingerprint=$(python3.11 -c 'import json,sys; print(json.load(open(sys.argv[1]))["review"]["fingerprint"])' "$manualWorkspace-review.json")
# Explicit trusted operator decision after review; resume immediately.
run_expected 0 python3.11 -m agent_tool_authority approve --workspace "$manualWorkspace" --request-id "$requestId" --fingerprint "$fingerprint" --ttl-seconds 60
run_expected 0 python3.11 -m agent_tool_authority resume --workspace "$manualWorkspace" --session support-agent --request-id "$requestId"
run_expected 4 python3.11 -m agent_tool_authority resume --workspace "$manualWorkspace" --session support-agent --request-id "$requestId"
run_expected 0 python3.11 -m agent_tool_authority audit --workspace "$manualWorkspace" --format jsonl
```

To reject instead, in a fresh run stop after review and invoke `reject --workspace ... --request-id ... --fingerprint ...` using those actual values. Only PENDING requests can be rejected. Session lifetime is 30 minutes; pending lifetime is at most five minutes; approval TTL is an integer 1–60 seconds, capped by session/pending deadlines. At `now >= expires_at` permission is unusable. Deadlines are rechecked after transaction lock acquisition and immediately before dispatch; they do not interrupt an executing adapter.

## Host integration

```python
from agent_tool_authority import OperatorService, open_workspace

gateway = open_workspace("work/manual")  # Trusted host configuration, initialized first.
agent_tools = gateway.agent("support-agent")  # Identity bound outside model output.
result = agent_tools.submit({
    "schema": "ata-call/v1",
    "tool": "tickets.read",
    "arguments": {"project": "support", "ticket_id": "T-100"},
})
# Expose only agent_tools.submit/resume to the model.
# Keep OperatorService(gateway) in the trusted operator channel.
```

The host must mediate every protected call. Model-generated identity or approval fields are rejected. Policy supports finite principal/tenant/project/tool/ticket/status scopes with DENY > APPROVAL_REQUIRED > ALLOW, default deny. Approval binds the canonical copied call, complete session, expected resource version and policy digest. A policy change invalidates old approvals; a validated policy snapshot is the decision boundary for an already executing call.

Host/operator/policy/database/adapter code are trusted. Same-user Python processes and private attributes provide no OS sandbox. Fingerprints are comparison IDs, not signatures; the database owner can edit audit. SQLite transactions protect only these local effects. There is no external exactly-once guarantee, prompt-injection prevention claim or security certification.

Read [architecture](docs/architecture.md), [contracts](docs/contracts.md), [threat model and limitations](docs/limitations.md), [contribution](docs/contribution.md), and [executed evidence](EVIDENCE.md). M1/M2 independently passed main review. M3 is submitted for whole-repository independent acceptance. MIT project license; runtime and CI attribution are in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

## Get the source

```sh
git clone https://github.com/sha-shank-03/agent-tool-authority.git
cd agent-tool-authority
```

Follow the quickstart above for runtime/dependency setup. Demos use fictional/mock data; initial dependency setup, where required, is separate from offline execution.
