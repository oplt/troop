#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request


def api_base() -> str:
    return os.environ.get("TROOP_API_BASE", "http://localhost:8000/api/v1").rstrip("/")


def call(method: str, path: str, payload: dict | None = None) -> dict:
    url = f"{api_base()}{path}"
    body = None
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url=url, method=method, data=body)
    req.add_header("Content-Type", "application/json")
    token = os.environ.get("TROOP_TOKEN")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise SystemExit(f"HTTP {exc.code}: {detail}") from exc


def cmd_task_create(args: argparse.Namespace) -> None:
    payload = {
        "title": args.title,
        "description": args.description or "",
        "priority": args.priority,
        "task_type": args.task_type,
        "github_issue_number": args.issue,
    }
    task = call("POST", f"/orchestration/projects/{args.project_id}/tasks", payload)
    print(json.dumps(task, indent=2))


def cmd_run_start(args: argparse.Namespace) -> None:
    payload = {
        "run_mode": args.run_mode,
        "model_name": args.model_name,
    }
    run = call("POST", f"/orchestration/projects/{args.project_id}/tasks/{args.task_id}/runs", payload)
    print(json.dumps(run, indent=2))


def cmd_run_stream(args: argparse.Namespace) -> None:
    last = 0
    terminal = {"completed", "failed", "cancelled", "blocked"}
    while True:
        events = call("GET", f"/orchestration/runs/{args.run_id}/events")
        for event in events[last:]:
            print(f"[{event.get('created_at')}] {event.get('event_type')}: {event.get('message')}")
        last = len(events)
        run = call("GET", f"/orchestration/runs/{args.run_id}")
        status = str(run.get("status") or "")
        if status in terminal:
            print(f"Run finished with status: {status}")
            break
        time.sleep(max(1, args.poll_seconds))


def main() -> None:
    parser = argparse.ArgumentParser(description="Troop CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    task_create = sub.add_parser("task-create", help="Create a task")
    task_create.add_argument("--project-id", required=True)
    task_create.add_argument("--title", required=True)
    task_create.add_argument("--description")
    task_create.add_argument("--priority", default="normal")
    task_create.add_argument("--task-type", default="general")
    task_create.add_argument("--issue", type=int, default=None)
    task_create.set_defaults(func=cmd_task_create)

    run_start = sub.add_parser("run-start", help="Start run for task")
    run_start.add_argument("--project-id", required=True)
    run_start.add_argument("--task-id", required=True)
    run_start.add_argument("--run-mode", default="single_agent")
    run_start.add_argument("--model-name", default=None)
    run_start.set_defaults(func=cmd_run_start)

    run_stream = sub.add_parser("run-stream", help="Stream run events (polling)")
    run_stream.add_argument("--run-id", required=True)
    run_stream.add_argument("--poll-seconds", type=int, default=2)
    run_stream.set_defaults(func=cmd_run_stream)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()

