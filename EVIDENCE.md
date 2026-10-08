# Executed evidence

Historical M1/M2 worker runs below were executed locally on **2026-10-07** and are preserved. M1 and M2 were subsequently independently accepted by main, recorded in `coordination/reviews/agent-tool-authority-M2.md` and `agent-tool-authority-M3.md`. M3 review-package verification is recorded separately below; whole-repository acceptance remains pending.

Working directory for every command: `C:/Users/shash/Documents/CodexPortfolios/agentic-ai-2026-10-07/agent-tool-authority`.
Environment observed: Windows/PowerShell, `py -3.11` -> CPython **3.11.9**, SQLite **3.45.1**. No packages, binaries, services or paid model calls were installed/used. No heavy build lease was needed for these bounded local checks.

## Commands and observations

| Command/check actually run | Observed result |
| --- | --- |
| Read AGENTS.md, own status and `coordination/reviews/agent-tool-authority-M1.md` | Main accepted the finite gateway plan and authorized only M1; no other worker files changed. |
| `py -3.11 -c "import sys,sqlite3; print(sys.version.split()[0]); print(sqlite3.sqlite_version)"` | Exit 0; Python 3.11.9, SQLite 3.45.1. |
| `py -3.11 -m agent_tool_authority --help` | Exit 0; seven commands listed: init/demo/submit/pending/approve/resume/audit; local mock/host trust label shown. |
| `py -3.11 -m unittest discover -s tests -v` | Exit 0; **13 tests passed**, runner reported 1.530 seconds. This is an observed test duration, not a performance benchmark. |
| `py -3.11 -m agent_tool_authority demo --workspace work/demo --json` | Exit 0; `assertions=passed`, `mode=scripted_mock`, `model_execution=none`, `paid_model_calls=0`, real local SQLite tools, explicit local operator simulation. |
| `py -3.11 -m agent_tool_authority audit --workspace work/demo --format jsonl` | Exit 0; **9 ordered `ata-audit/v1` rows**, including policy decisions, pending request, operator approval, version-2 execution and consumed-grant replay refusal. |
| Separate PowerShell CLI journey under `work/manual` | Native exits: init 0, read 0, close **4**, resolve **3**, pending review 0, approve 0, first resume 0, replay **4**, audit 0. Script asserted all codes/state; exit 0. |
| Repeat `demo --workspace work/demo --json` | `WORKSPACE_EXISTS`, no overwrite. A direct PowerShell command wrapper reported process exit 1 for the native failure; a subsequent `$LASTEXITCODE` assertion confirmed the **native CLI exit is 2**. Both observations are recorded, not conflated. |
| Read-only SQLite state probes for `work/demo` and `work/manual` | In both: acme-lab/T-100 = resolved/version 2; acme-lab/T-200 and other-lab/T-100 = open/version 1; one approval request = CONSUMED. |
| Python source whitespace check | Exit 0; 11 source/test files, no trailing whitespace. |
| Git/file inventory | New local M1 files present, ignored generated workspaces/cache excluded. Git still has no commits; no publication/push performed. |

The manual CLI script used the actual pending request ID and reviewed fingerprint from the immediately preceding output. It invoked the separate local operator CLI; this demonstrates the interface and is not evidence of an authenticated enterprise user or a model-driven approval. A compact scratch record is retained at `work/m1-manual-evidence.json` (ignored). README uses fresh GUID paths so rerunning the documented commands preserves prior evidence workspaces.

## State assertions actually observed

```json
{
  "before_approval": {"status": "open", "version": 1},
  "after_approval": {"status": "resolved", "version": 2},
  "denied_close": "DENY/NOT_EXECUTED",
  "pending_resolve": "APPROVAL_REQUIRED/NOT_EXECUTED",
  "replay": "APPROVAL_CONSUMED/NOT_EXECUTED",
  "tool_invocations": {"tickets.read": 1, "tickets.set_status": 1},
  "audit_rows": 9
}
```

The test suite additionally observed: allowed triage affects only the bound tenant; pending and operator approval cause zero adapter invocations/mutation; model-facing facade has no approve method; forged approval/identity fields and an approval-tool request are refused; unmatched finite scope defaults to deny; another tenant's same ticket ID cannot satisfy lookup; caller edits cannot mutate a stored pending payload; wrong review fingerprint cannot approve; changed ticket version blocks resume before adapter dispatch; invalid policy/session fail closed; an expired session cannot dispatch; reinitializing a populated workspace preserves it. Assertions inspect real SQLite state, adapter counters, grant states and audit events.

## What this evidence does not establish

At the original M1 submission, grant/pending expiration boundary cases, policy drift, rejection, malformed/duplicate/oversized frames, simultaneous resume, adapter/audit/storage failure injection and controlled process termination/harness faults were unexecuted. They were then explicitly assigned as M2; their observed outcomes are recorded below.

At the historical M1 submission, M3 documents/CI were not implemented and M2 independent verification was pending. M3 documents/CI are now prepared, and main independently accepted M2. No hosted CI job, Linux execution, Python 3.12 compatibility suite, live model evaluation, recorded model replay, security audit, benchmark, external connector or real account change was run.

Host/operator trust and supported-path mediation are prerequisites. Same-user Python processes are not sandboxed; a host owner can bypass the library or edit audit/state. Local SQLite atomic commit does not prove exactly-once external side effects, power-loss behavior, tamper-proof audit, or general security.

## M2 commands and observed outcomes

Main's explicit M2 assignment was read from `coordination/reviews/agent-tool-authority-M2.md`. Implementation and all artifacts remain in the exclusive repository/worker record. Tests use the same observed CPython **3.11.9** / SQLite **3.45.1**, Python standard library only. Bounded local process/SQLite tests required no heavy lease.

| Command/check actually run | Observed result |
| --- | --- |
| `py -3.11 -m unittest discover -s tests -v` (first M2 suite) | Exit 0; **42 tests passed**, reported 9.350 seconds. |
| Same command after adding expired-pending/session-cap and non-finite-number checks | Exit 0; **44 tests passed**, reported **9.425 seconds**. Includes all 13 M1 tests. Durations are observations, not benchmarks. |
| CLI demo on fresh `work/m2-demo-ed5e723e67b24d1e8562497a7d91903b` | Exit 0, `assertions=passed`, scripted mock/zero model calls/real SQLite. Before open/version 1; after resolved/version 2; one read and one status adapter dispatch; replay refused. |
| CLI audit for that demo | Exit 0; **9 ordered audit rows**. Scratch summary saved in `work/m2-demo-receipt.json`. |
| `py -3.11 -m agent_tool_authority reject --help` | Exit 0; request ID and review fingerprint required. |
| Separate real CLI rejection journey on fresh `work/m2-reject-13fd60c42f054013a44100bbf3a42dcb` | Native exits init **0**, pending submit **3**, review **0**, reject **0**, resume **4**, approve **4**, audit **0**. Assertions passed; rejected/resume code `REJECTED` / `APPROVAL_UNUSABLE`; **6 audit rows**, zero TOOL_EXECUTED rows. |
| Direct read-only SQLite probe of rejection workspace | Request `REJECTED`; all three tickets open/version 1. Scratch receipt: `work/m2-reject-receipt.json`. |
| Process receipt reads | Actual child reaping, pipe-thread completion, staged-versus-persisted commit outcomes observed as described below. |

### Semantic authorization and failure assertions

- Session/pending/grant boundaries: a session/read and grant/resume work immediately before their deadlines and fail at the deadline. Pending expiration is terminal on resume/approve; pending/grant deadline is capped by the trusted session. Clock is acquired after the SQLite write lock and rechecked immediately before dispatch. Expiration caused **zero adapter calls** in the refusal cases.
- Explicit rejection: reviewed fingerprint required; incorrect fingerprint leaves the request pending; rejection becomes terminal. Another session receives a generic unavailable response with no action/request payload and cannot consume the grant. Invalid TTLs cannot widen approval.
- Drift: changed policy (even a looser one), stored action, trusted session binding, or ticket version prevents dispatch. Detected policy/action/version drift makes the request unusable and requires a fresh request. Caller-side mutation cannot alter an immutable pending payload.
- Precedence: all six orderings of matching allow/approval/deny yield denial; both allow/approval orderings require approval; empty policy defaults to deny. Diagnostics report the winning determining rule IDs.
- Strict input: malformed/duplicate-key/oversized/non-UTF-8/non-finite JSON, invalid call/session/policy types, unknown fields/schemas, duplicate scopes and missing exact permissions fail closed. Three malformed request files were also refused by real CLI processes with native exit 2.
- Adapter failure: a local adapter updated the ticket and then raised; ticket update rolled back, grant became FAILED, and one TOOL_FAILED audit persisted. No execution audit or exception body leaked into exported audit.
- Audit failure: injected SQLite error during execution audit rolled back both ticket update and grant consumption; grant remained APPROVED and prior audit unchanged. Retry after restoring writable audit committed one local mutation and one execution audit. Adapter dispatch can repeat after rollback; no exactly-once invocation claim.
- Unavailable storage/denial audit failure: return STORAGE_ERROR with zero dispatch and no invented durable audit row. A trusted harness telemetry attempt reported false when it could not persist.
- Two connections resumed the same approved action from a barrier: exactly one EXECUTED and one APPROVAL_CONSUMED result; total status dispatches **1**, local version **2**, grant CONSUMED, **one persisted execution audit**. Reopening retained the audit and refused replay. Separate tests reopened a pending request, approved it, reopened again, and resumed successfully.

### Actual blocked pipe and direct-child cleanup

Final receipt `work/m2-stdin-stall-receipt.json`: synthetic host reply below the 16 KiB frame limit, real worker that never reads stdin; **attempted writes 1, completed writes 0**, last phase **WRITE**, reason DEADLINE, observed elapsed **1.0 seconds** for a one-second test deadline. The direct Windows child was killed/reaped with return code 1; reader and writer threads were both no longer alive. This proves the tested write-side stall did not block the supervising thread indefinitely.

`work/m2-harness-receipts.json` contains the real hung, oversized, duplicate-key malformed, non-UTF-8, and excess-call fixture outcomes. All direct children were killed/reaped and both I/O threads ended. Invalid/oversized/hung cases dispatched **0** adapters; the excess-call worker dispatched exactly **8** authorized reads and its ninth call was refused. A separate malformed-worker test persisted HARNESS_FAILED after cleanup. Fixtures are trusted self-authored code generating synthetic faults, never model execution or hostile-code isolation.

The supervisor uses one monotonic exchange deadline for input, write/flush acknowledgements and child exit, plus up to three seconds for child/thread cleanup. It controls the direct child only. Failure-audit persistence can add the store's bounded busy wait. It does not guarantee cancellation of arbitrary trusted adapters, descendants, OS-level resource exhaustion, or hardware/filesystem stalls.

### Actual termination around local commit

`work/m2-commit-receipts.json` records two explicit checkpoints. Child processes were killed by the parent only after reaching their checkpoint and reaped before reopening. These are controlled **process** terminations, not simulated power loss or OS crashes.

| Checkpoint | Inside child before kill | Persisted after kill/reopen | Retry |
| --- | --- | --- | --- |
| Before SQLite COMMIT | Staged ticket version 2, grant CONSUMED, one staged execution audit | Ticket version **1**, grant **APPROVED**, **0** execution audits; transaction rolled back | EXECUTED, final version 2/CONSUMED/one execution audit |
| After SQLite COMMIT, before response | Ticket version 2, grant CONSUMED, one execution audit | Ticket version **2**, grant **CONSUMED**, **1** execution audit; transaction committed | APPROVAL_CONSUMED, no additional update |

Each final store had version 2, CONSUMED state and one committed execution audit. The test illustrates uncertain caller response after commit and supported-path replay refusal; it is not an external exactly-once guarantee.

### Additional primary implementation references

Actually read **2026-10-07**: [Python subprocess](https://docs.python.org/3.11/library/subprocess.html), [threading](https://docs.python.org/3.11/library/threading.html), and [bounded queue operations](https://docs.python.org/3.11/library/queue.html). The subprocess reference documents pipe deadlock risks, the need to kill/wait after timeout, and Windows termination behavior. The online 3.11 documentation currently renders 3.11.17; implementation remains on the installed 3.11.9 API baseline. No documentation code is copied or new dependency introduced.

At the historical M2 submission, M3 and main independent M2 verification were pending. Main subsequently independently passed M2: 44 tests, fresh demo, six separate rejection CLI processes and direct SQLite observations. Main-owned receipts are `coordination/acceptance/agent-tool-authority/m2-main-tests.json`, `m2-main-probes-20261008/summary.json`, and `m2-main-demo.json`. The main probe initially used an incorrect .db extension and then corrected it to `authority.sqlite3`; that failed probe remains preserved in main's evidence without worker product changes.

Remaining unexecuted: hosted CI, POSIX/Linux, Python 3.12 compatibility, live model or recorded model evaluations, external tools, production/account changes, performance/security benchmarks, descendant-process containment and real OS crash/power-loss behavior. M3 independent whole-repository acceptance is pending.

## M3 review package and actual Windows verification

Executed **2026-10-08**, same repository cwd and explicit `py -3.11` selector. Observed interpreter: `C:/Users/shash/AppData/Local/Microsoft/WindowsApps/PythonSoftwareFoundation.Python.3.11_qbz5n2kfra8p0/python.exe`, CPython **3.11.9**, SQLite **3.45.1**, platform string `Windows-10-10.0.26200-SP0`. The worker read the accepted `coordination/reviews/agent-tool-authority-M3.md` assignment. M3 adds documentation, two review scripts and prepared CI only; application, test and example behavior was not changed. No dependency/runtime installation, heavy workload, paid call, external account write, publication, push or deployment occurred.

| Actual command/check | Exit and observed outcome |
| --- | --- |
| PowerShell `Parser.ParseFile` on `scripts/manual_operator.ps1`; Python `ast.parse` on the verifier | Exit 0; both parse successfully. |
| `py -3.11 scripts/verify_repository.py` | Exit **0**, all assertions passed. Existing **44 tests** passed; unittest reported **7.956 seconds**. This is an observation, not a benchmark. **20 native child commands** met their explicitly expected exits. |
| Verifier fresh demo + audit | Exits 0/0; scripted mock, no model/replay/paid calls, real SQLite; open1 -> resolved2 once; read/status counters 1 each; CONSUMED; nine ordered audit rows. |
| Verifier rerun demo in its populated workspace | Native exit **2**, WORKSPACE_EXISTS; exact before/after SQL snapshot unchanged. |
| Verifier separate approval CLI journey | Exits **0/0/4/3/0/0/0/4/0** for init/read/close/resolve/review/approve/resume/replay/audit. Direct SQL observed open1/PENDING before operator, open1/APPROVED after approval, resolved2/CONSUMED after resume/replay, one mutation audit. Both unrelated fixture tickets stayed open1. |
| Verifier separate rejection CLI journey | Exits **0/3/0/0/4/4/0** for init/resolve/review/reject/resume/refused-approve/audit. Direct SQL observed REJECTED; all three tickets stayed open1; zero mutation audits; six ordered audit rows matching export. |
| Documented `& ./scripts/manual_operator.ps1` | PowerShell execution exit **0**, same nine native exits as approval above; exact stored action printed and checked, actual request ID/fingerprint used, explicit local operator approval, successful one resume, APPROVAL_CONSUMED replay. |
| README standalone Windows version guard, fresh GUID demo and audit commands | Exits **0/0/0**; demo assertions passed, nine audit rows. Cwd/interpreter/native argv and stdout retained in the fresh workspace. |
| `py -3.11 work/m3_package_check.py` | Exit **0**; verified all native exits/output hashes, before/after source manifests, six prior raw receipt hashes, manual/quickstart final SQL state, **16 Python AST files**, **10 local documentation links**, source whitespace and workflow pins/configuration. Workflow check was manual/text review, not a hosted YAML engine/schema execution. |
| `git diff --check`; `git status --short --branch` | Exit 0; no tracked diffs (repo still has no commits); expected new local package files present. The separate source whitespace check covers untracked files. |

The verifier ran from 02:13:18 to 02:13:31 UTC. Its receipt has exact executable argv arrays, command cwd, timeout/exit/duration, raw stdout/stderr paths and their SHA-256 hashes, real SQL snapshots, and SHA-256 of **34 source/package files** before/after. All 34 hashes stayed identical during execution. The final evidence text and official-source links were updated after that run; `work/m3-final-manifest.json` captures the initial M3 package hashes and identifies those documentation changes. At that initial submission, application/tests/examples/verifier/manual script/workflow matched the files actually exercised. The subsequent bounded shell-probe correction is recorded below with its own manifest; the original manifest is preserved. Source digests identify observed files; they are not signatures.

Local raw evidence (ignored, retained in this repository):

- `work/verification/20261008T021318Z-9c144af18f7d4af4a27f15c7fc8f1b97/receipt.json`, per-command stdout/stderr, `prior_receipts/` and `fresh_process_receipts/`;
- `work/manual-m3-7c5c397b51e3407da4e08d3b00922b00/receipt.json`, `commands.json`, `commands/*.stdout.txt`/`*.stderr.txt`;
- `work/demo-afade7f7922147a89328a58271acdace/quickstart-receipt.json`, `demo.stdout.txt`, `audit.stdout.txt`;
- `work/m3-package-check-receipt.json`, `work/m3-final-manifest.json` and their self-authored local inspection scripts.

All six prior M1/M2 scratch receipts were copied byte-for-byte before the test suite overwrote its generated M2 scratch files. The fresh stalled-stdin receipt again observed one attempted write, zero completed writes, WRITE/DEADLINE at 1.0 seconds, direct child reaped and both I/O threads ended. The fresh controlled commit receipts again observed before-COMMIT rollback (version1/APPROVED/audit0) versus after-COMMIT persistence (version2/CONSUMED/audit1), and the expected retry outcomes. These are controlled fixture/process observations, not OS sandboxing or power-loss guarantees.

Initial M3 exercised review/CI file SHA-256 (the corrected manual-script hash follows below):

| File | SHA-256 |
| --- | --- |
| `scripts/verify_repository.py` | `51488a477ca7f82449ac05babd9f8629ac0f3bfa41bc2439de6446876e1dd82f` |
| `scripts/manual_operator.ps1` | `0c7011ef6ca3b7bee90d0d2bc542fb1cd85e7ace36439bc58a0288ef0232feed` |
| `.github/workflows/ci.yml` | `cfecb5f199bc2a3037a61a77e4a89d2a1dfc32ba05b61871d2c20cace3fcc151` |

Prepared CI uses the immutable commits recorded in PLAN.md/attribution, exact Python 3.11.9, read-only contents permission, no persisted checkout credentials, two standard Windows/Linux jobs with five-minute limits, and the same offline verifier with expected-negative gates. Primary [checkout declaration](https://raw.githubusercontent.com/actions/checkout/3d3c42e5aac5ba805825da76410c181273ba90b1/action.yml), [setup-python declaration](https://raw.githubusercontent.com/actions/setup-python/5fda3b95a4ea91299a34e894583c3862153e4b97/action.yml), pinned MIT licenses, [runner image list](https://raw.githubusercontent.com/actions/runner-images/main/README.md) and [public standard-runner billing documentation](https://docs.github.com/en/billing/concepts/product-billing/github-actions) were actually read on 2026-10-08. Availability and prepared configuration are distinct from hosted execution.

M3 docs/attribution/CI/review scripts and bounded local verification are complete for submission. **Main's independent whole-repository acceptance is pending.** Hosted CI, POSIX/Linux command execution, Python 3.12 compatibility, live model/recorded model evaluation, remote connectors, external effects, security/performance assurance, descendant containment and OS-crash/power-loss behavior remain unexecuted/unestablished. All mock tools here are freshly invoked local SQLite adapters; no authored transcript is represented as a recorded model replay or fresh model run.

## M3 correction 1: actual two-shell operator journeys

Main's independent final review found an actual shell compatibility defect. Original `powershell.exe -NoProfile -File scripts/manual_operator.ps1` exited **1** on this HP: embedded double quotes in the Python runtime-probe argument were lost, producing `NameError: name 'executable' is not defined` before any workspace action. Main's original PowerShell 7.6.5 invocation passed. Both main-owned receipts remain untouched and were copied into the worker's new correction directory. The accepted `agent-tool-authority-M3-correction1.md` assignment authorized only the probe correction and bounded manual checks.

Only **line 5** of `scripts/manual_operator.ps1` changed: `json.dumps(dict(executable=sys.executable, python=sys.version.split()[0], sqlite=sqlite3.sqlite_version))` replaces quoted dictionary-key literals. The complete script before the edit and prior final manifest are preserved. Application, tests, fixtures, verifier, approval policy and workflow are unchanged; no full unit rerun was performed or needed for this script-only correction. The earlier 44-test/20-command verifier evidence remains applicable to those unchanged sources.

| Actual command/check, same repo cwd | Observed result |
| --- | --- |
| First `py -3.11 work/m3_correction1_check.py` | Exit **1**; corrected runtime probe passed in Python-launched Windows PowerShell, then `Get-FileHash` was unavailable during source-hash preflight. No authority CLI action ran. Raw failure and receipt preserved; not counted as a successful journey. |
| `C:/windows/System32/WindowsPowerShell/v1.0/powershell.exe -NoProfile -File scripts/manual_operator.ps1`, invoked natively from PowerShell 7.6.5 | Exit **0**; actual shell **5.1.26100.9444**; nine native CLI exits **0/0/4/3/0/0/0/4/0**. Actual review ID/fingerprint, explicit operator approval, one resume, APPROVAL_CONSUMED/NOT_EXECUTED replay. |
| `C:/Users/shash/.cache/codex-runtimes/codex-primary-runtime/dependencies/native/powershell/pwsh.exe -NoProfile -File scripts/manual_operator.ps1`, same native launcher | Exit **0**; actual shell **7.6.5**; same nine expected native exits and outcomes. |
| `py -3.11 work/m3_correction1_inspect.py` | Exit **0**; checked both raw shell runs, source hashes, native exits and direct read-only SQLite snapshots: each has acme-lab/support/T-100 resolved/version **2**, request **CONSUMED**, exactly **one** mutation audit, **nine** ordered audit rows, other tickets open1 and replay refused. Proved only script line 5 changed before the runs, with unchanged core/test/verifier/CI hashes. |
| `py -3.11 work/m3_shell_environment_probe.py` | Runner exit 0; read-only diagnostic child exit **1** because Get-FileHash was absent. Observed inherited PowerShell 7 module paths in Python-launched Windows PowerShell. Passing native launch's recorded effective module paths were Windows PowerShell paths. This is an environment qualification, not a further script/runtime change. |

Both successful journeys used actual CPython **3.11.9** / SQLite **3.45.1**. The native shell run record contains actual shell executable/argv/cwd/version probe argv, exit/duration and corrected script SHA-256. Each manual receipt contains the native CLI argv/exits, interpreter and source hashes; inspection records SQL state and raw-file SHA-256. Corrected script hash: `c1fa72006503ae3d26c32d7612efcc9aba5463e0bfad94698fff523b372a40f4`.

Preserved correction evidence is under `work/m3-correction1-69831d0cf5644b9b865f45fc08f5c7a1/`: `main-original-failure.json`, `main-original-pwsh-pass.json`, `manual_operator.before.ps1`, `prior-final-manifest.json`, failed `correction-receipt.json`, `native-shell-runs.json` plus raw version/manual stdout/stderr, `two-shell-inspection.json`, `python-launched-environment.json` plus diagnostic streams, and `final-manifest.json`. New actual successful manual receipts: `work/manual-m3-c8c4f302e7514451af5d912a7a05739a/receipt.json` (Windows PowerShell 5.1) and `work/manual-m3-4409c994368d4059a7fcb507ec2aa99c/receipt.json` (PowerShell 7). No earlier evidence was overwritten.

The correction final manifest identifies the final source bytes after shell-tested documentation updates and preserves exact raw evidence hashes. Main whole-repository acceptance remains pending. All previously stated unexecuted checks/limitations remain; no dependency, paid call, account write, publication, push, deployment, heavy lease or new product feature was added.
