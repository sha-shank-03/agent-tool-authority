"""CLI is the trusted host/operator surface; JSON request files are untrusted."""

import argparse
import json
import sqlite3
from pathlib import Path

from .contracts import MAX_FRAME, AuthorityError, canonical, parse_json
from .gateway import OperatorService, error_result
from .harness import demo
from .workspace import initialize, open_workspace


def parser():
    cli = argparse.ArgumentParser(
        description="Local scoped tool gateway. Demo is scripted mock execution with real SQLite tools; host/operator trusted.")
    sub = cli.add_subparsers(dest="command", required=True)
    for name, help_text in (
        ("init", "Initialize a NEW local fixture workspace"),
        ("demo", "Assert allowed/denied/pending/operator/resume/replay scripted mock journey"),
        ("submit", "Submit untrusted call JSON under a host-bound session"),
        ("pending", "Operator: inspect exact stored action and review fingerprint"),
        ("approve", "Operator: explicitly approve a reviewed fingerprint"),
        ("reject", "Operator: explicitly reject a reviewed pending action"),
        ("resume", "Agent: execute a stored approved action once"),
        ("audit", "Operator: export ordered local audit JSONL"),
    ):
        command = sub.add_parser(name, help=help_text)
        command.add_argument("--workspace", required=True, type=Path)
        if name in {"submit", "resume"}:
            command.add_argument("--session", required=True)
        if name == "submit":
            command.add_argument("--request", required=True, type=Path)
        if name in {"pending", "approve", "reject", "resume"}:
            command.add_argument("--request-id", required=True)
        if name in {"approve", "reject"}:
            command.add_argument("--fingerprint", required=True)
        if name == "approve":
            command.add_argument("--ttl-seconds", type=int, default=60)
        if name == "audit":
            command.add_argument("--format", choices=["jsonl"], default="jsonl")
        if name == "demo":
            command.add_argument("--json", action="store_true", help="Compact JSON summary")
    return cli


def exit_code(result):
    return {"ALLOW": 0, "ERROR": 2, "APPROVAL_REQUIRED": 3, "DENY": 4}[result["decision"]]


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        if args.command == "init":
            result = {"decision": "ALLOW", "code": "INITIALIZED", "workspace": str(initialize(args.workspace)),
                      "mode": "local_fixture", "session_lifetime_seconds": 1800}
        elif args.command == "demo":
            result = demo(args.workspace)
        else:
            gateway = open_workspace(args.workspace)
            if args.command == "submit":
                with args.request.open(encoding="utf-8") as stream:
                    call = parse_json(stream.read(MAX_FRAME + 1))
                result = gateway.agent(args.session).submit(call)
            elif args.command == "resume":
                result = gateway.agent(args.session).resume(args.request_id)
            elif args.command == "pending":
                result = OperatorService(gateway).pending(args.request_id)
            elif args.command == "approve":
                result = OperatorService(gateway).approve(args.request_id, args.fingerprint, args.ttl_seconds)
            elif args.command == "reject":
                result = OperatorService(gateway).reject(args.request_id, args.fingerprint)
            else:
                for row in gateway.store.audit():
                    print(canonical(row))
                return 0
        print(json.dumps(result, sort_keys=True, indent=None if getattr(args, "json", False) else 2))
        return 0 if args.command == "demo" else exit_code(result)
    except AuthorityError as exc:
        print(canonical(error_result(exc.code)))
        return exit_code(error_result(exc.code))
    except (OSError, UnicodeError, sqlite3.Error):
        print(canonical(error_result("STORAGE_ERROR")))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
