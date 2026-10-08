"""Offline review/CI checks; no model, network, package install or product behavior."""

import hashlib
import json
import platform
import shutil
import sqlite3
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROCESS_RECEIPTS = (
    "m2-harness-receipts.json", "m2-stdin-stall-receipt.json", "m2-commit-receipts.json",
    "m2-demo-receipt.json", "m2-reject-receipt.json", "m1-manual-evidence.json",
)


def source_hashes():
    paths = [p for p in ROOT.iterdir() if p.is_file()]
    for directory in ("agent_tool_authority", "tests", "examples", "scripts", "docs", ".github"):
        paths.extend(p for p in (ROOT / directory).rglob("*")
                     if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc")
    return {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(paths)}


def require(condition, description):
    if not condition:
        raise AssertionError(description)


def snapshot(workspace):
    database = (workspace / "authority.sqlite3").resolve()
    con = sqlite3.connect(database.as_uri() + "?mode=ro", uri=True, timeout=1)
    con.row_factory = sqlite3.Row
    try:
        return {
            "tickets": [dict(row) for row in con.execute("SELECT * FROM tickets ORDER BY tenant,project,id")],
            "requests": [dict(row) for row in con.execute(
                "SELECT id,state,fingerprint,pending_expires_at,grant_expires_at FROM requests ORDER BY id")],
            "audit": [{"sequence": row["sequence"], **json.loads(row["event_json"])}
                      for row in con.execute("SELECT * FROM audit ORDER BY sequence")],
        }
    finally:
        con.close()


def assert_state(state, status, version, request_state, mutations):
    expected = [
        {"tenant": "acme-lab", "project": "support", "id": "T-100", "status": status, "version": version},
        {"tenant": "acme-lab", "project": "support", "id": "T-200", "status": "open", "version": 1},
        {"tenant": "other-lab", "project": "support", "id": "T-100", "status": "open", "version": 1},
    ]
    require(state["tickets"] == expected, "Exact fixture ticket state/tenant separation")
    require([r["state"] for r in state["requests"]] == [request_state], "Stored request state")
    audit = state["audit"]
    require([r["sequence"] for r in audit] == list(range(1, len(audit) + 1)), "Ordered audit sequence")
    require(all(r["schema"] == "ata-audit/v1" for r in audit), "Audit schema")
    executed = [r for r in audit if r["event"] == "TOOL_EXECUTED" and r["tool"] == "tickets.set_status"]
    require(len(executed) == mutations, "Exactly expected committed mutation audits")


class Verification:
    def __init__(self):
        self.directory = ROOT / "work" / "verification" / (
            datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ-") + uuid.uuid4().hex)
        self.directory.mkdir(parents=True)
        self.receipt = {
            "schema": "ata-verification/v1", "started_at_utc": datetime.now(timezone.utc).isoformat(),
            "entry_argv": [sys.executable, *sys.argv], "cwd": str(Path.cwd()), "command_cwd": str(ROOT),
            "interpreter": sys.executable, "python": platform.python_version(),
            "platform": platform.platform(), "sqlite": sqlite3.sqlite_version,
            "mode": "fresh_scripted_mock_and_local_cli", "model_execution": "none",
            "recorded_model_replay": False, "paid_model_calls": 0,
            "source_sha256_before": source_hashes(), "commands": [], "snapshots": {},
            "hosted_ci_result": "not_observed_by_this_script", "assertions": "in_progress",
        }

    def archive(self, label):
        target = self.directory / label
        target.mkdir()
        hashes = {}
        for name in PROCESS_RECEIPTS:
            source = ROOT / "work" / name
            if source.is_file():
                shutil.copy2(source, target / name)
                hashes[name] = hashlib.sha256(source.read_bytes()).hexdigest()
        self.receipt[label] = hashes

    def run(self, label, arguments, expected=0, timeout=20, jsonl=False):
        argv = [sys.executable, *arguments]
        started = time.monotonic()
        record = {"label": label, "argv": argv, "cwd": str(ROOT), "expected_exit": expected,
                  "timeout_seconds": timeout, "stdout": label + ".stdout.txt", "stderr": label + ".stderr.txt"}
        self.receipt["commands"].append(record)
        try:
            completed = subprocess.run(argv, cwd=ROOT, capture_output=True, timeout=timeout)
            stdout, stderr = completed.stdout, completed.stderr
            record.update(exit_code=completed.returncode, timed_out=False)
        except subprocess.TimeoutExpired as exc:
            stdout, stderr = exc.stdout or b"", exc.stderr or b""
            record.update(exit_code=None, timed_out=True)
        record["elapsed_seconds"] = time.monotonic() - started
        (self.directory / record["stdout"]).write_bytes(stdout)
        (self.directory / record["stderr"]).write_bytes(stderr)
        record.update(stdout_sha256=hashlib.sha256(stdout).hexdigest(), stderr_sha256=hashlib.sha256(stderr).hexdigest())
        print(f"{label}: expected={expected} actual={record['exit_code']}", flush=True)
        require(not record["timed_out"] and record["exit_code"] == expected, label + " native exit")
        if arguments[:2] == ["-m", "unittest"]:
            sys.stdout.write(stderr.decode("utf-8", errors="replace"))
            return None
        text = stdout.decode("utf-8")
        return [json.loads(line) for line in text.splitlines()] if jsonl else json.loads(text)

    def cli(self, label, workspace, command, *arguments, expected=0, jsonl=False):
        return self.run(label, ["-m", "agent_tool_authority", command, "--workspace", str(workspace),
                               *arguments], expected=expected, jsonl=jsonl)

    def save_state(self, label, workspace):
        state = snapshot(workspace)
        self.receipt["snapshots"][label] = state
        return state

    def journey(self, decision):
        workspace = self.directory / decision
        self.cli(decision + "-init", workspace, "init")
        if decision == "approve":
            read = self.cli("approve-read", workspace, "submit", "--session", "support-agent",
                            "--request", "examples/requests/read.json")
            require(read["execution"] == "EXECUTED" and read["output"]["version"] == 1, "Allowed real read")
            denied = self.cli("approve-close", workspace, "submit", "--session", "support-agent",
                              "--request", "examples/requests/close.json", expected=4)
            require(denied["decision"] == "DENY" and denied["execution"] == "NOT_EXECUTED", "Denied close")
        pending = self.cli(decision + "-pending", workspace, "submit", "--session", "support-agent",
                           "--request", "examples/requests/resolve.json", expected=3)
        require(pending["code"] == "APPROVAL_REQUIRED" and pending["execution"] == "NOT_EXECUTED", "Pending no dispatch")
        request_id = pending["request_id"]
        review = self.cli(decision + "-review", workspace, "pending", "--request-id", request_id)["review"]
        require(review["state"] == "PENDING" and review["fingerprint"] == pending["fingerprint"], "Actual stored review")
        require(review["action"]["call"] == json.loads((ROOT / "examples/requests/resolve.json").read_text()), "Exact reviewed call")
        assert_state(self.save_state(decision + "-before", workspace), "open", 1, "PENDING", 0)
        result = self.cli(decision + "-operator", workspace, decision, "--request-id", request_id,
                          "--fingerprint", review["fingerprint"])
        require(result["code"] == ("APPROVED" if decision == "approve" else "REJECTED"), "Operator transition")
        assert_state(self.save_state(decision + "-after-operator", workspace), "open", 1,
                     "APPROVED" if decision == "approve" else "REJECTED", 0)
        resumed = self.cli(decision + "-resume", workspace, "resume", "--session", "support-agent",
                           "--request-id", request_id, expected=0 if decision == "approve" else 4)
        require(resumed["code"] == ("EXECUTED" if decision == "approve" else "APPROVAL_UNUSABLE"), "Resume outcome")
        if decision == "approve":
            replay = self.cli("approve-replay", workspace, "resume", "--session", "support-agent",
                              "--request-id", request_id, expected=4)
            require(replay["code"] == "APPROVAL_CONSUMED" and replay["execution"] == "NOT_EXECUTED", "Replay refused")
        else:
            refused = self.cli("reject-approve-refused", workspace, "approve", "--request-id", request_id,
                               "--fingerprint", review["fingerprint"], expected=4)
            require(refused["code"] == "APPROVAL_UNUSABLE", "Rejected request cannot approve")
        state = self.save_state(decision + "-final", workspace)
        assert_state(state, "resolved" if decision == "approve" else "open", 2 if decision == "approve" else 1,
                     "CONSUMED" if decision == "approve" else "REJECTED", 1 if decision == "approve" else 0)
        exported = self.cli(decision + "-audit", workspace, "audit", "--format", "jsonl", jsonl=True)
        require(exported == state["audit"], "Export matches direct read-only SQLite observation")

    def execute(self):
        self.archive("prior_receipts")  # Existing tests rewrite their scratch receipts; preserve originals first.
        require(platform.python_version() == "3.11.9", "Select the documented exact Python 3.11.9 baseline")
        self.run("tests", ["-m", "unittest", "discover", "-s", "tests", "-v"], timeout=60)
        self.archive("fresh_process_receipts")
        workspace = self.directory / "demo"
        demo = self.cli("demo", workspace, "demo", "--json")
        require(demo["assertions"] == "passed" and demo["mode"] == "scripted_mock"
                and demo["model_execution"] == "none" and demo["recorded_replay"] is False
                and demo["paid_model_calls"] == 0, "Fresh mock disclosure")
        require(demo["before_approval"] == {"status": "open", "version": 1}
                and demo["after_approval"] == {"status": "resolved", "version": 2}, "Demo local mutation")
        require(demo["tool_invocations"] == {"tickets.read": 1, "tickets.set_status": 1}, "Demo exact adapter counts")
        state = self.save_state("demo-final", workspace)
        assert_state(state, "resolved", 2, "CONSUMED", 1)
        exported = self.cli("demo-audit", workspace, "audit", "--format", "jsonl", jsonl=True)
        require(exported == state["audit"] and len(exported) == demo["audit_rows"] == 9, "Demo audit")
        refused = self.cli("demo-existing-workspace", workspace, "demo", "--json", expected=2)
        require(refused["code"] == "WORKSPACE_EXISTS" and snapshot(workspace) == state, "Preserve existing workspace")
        self.journey("approve")
        self.journey("reject")
        require(source_hashes() == self.receipt["source_sha256_before"], "Sources unchanged during verification")
        self.receipt["assertions"] = "passed"


def main():
    verification = Verification()
    code = 0
    try:
        verification.execute()
    except Exception as exc:
        code = 1
        verification.receipt.update(assertions="failed", failure={"type": type(exc).__name__, "message": str(exc)})
        print(f"Verification failed: {type(exc).__name__}: {exc}", file=sys.stderr)
    finally:
        verification.receipt.update(finished_at_utc=datetime.now(timezone.utc).isoformat(), exit_code=code,
                                    source_sha256_after=source_hashes())
        receipt_path = verification.directory / "receipt.json"
        receipt_path.write_text(json.dumps(verification.receipt, indent=2) + "\n", encoding="utf-8")
        print(f"receipt: {receipt_path}", flush=True)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
