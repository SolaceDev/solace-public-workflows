#!/usr/bin/env python3
"""Dispatch a workflow_dispatch workflow and optionally wait for completion."""

from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _bootstrap_common_module() -> None:
    script_path = Path(__file__).resolve()
    for parent in script_path.parents:
        candidate = parent / "common" / "github_reporting.py"
        if candidate.exists():
            sys.path.insert(0, str(candidate.parent))
            return


_bootstrap_common_module()

from github_reporting import github_api, write_output  # type: ignore  # noqa: E402


WORKFLOW_RUN_STATUS_COMPLETED = "completed"
FAILING_CONCLUSIONS = {"failure", "cancelled", "timed_out"}
TIMESTAMPED_LOG_LINE = re.compile(r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{7}Z)\s+(.*)")


def debug(message: str, payload: Any | None = None) -> None:
    if os.getenv("RUNNER_DEBUG") != "1":
        return

    if payload is None:
        print(f"::debug::{message}")
        return

    try:
        rendered = json.dumps(payload, indent=2, sort_keys=True)
    except Exception:
        rendered = str(payload)
    print(f"::group::{message}")
    print(f"::debug::{rendered}")
    print("::endgroup::")


def parse_bool(value: str, *, default: bool = False) -> bool:
    if value is None:
        return default
    stripped = value.strip()
    if not stripped:
        return default
    return stripped.lower() == "true"


def to_milliseconds(value: str) -> int:
    stripped = (value or "").strip()
    if len(stripped) < 2:
        raise ValueError(f"Invalid duration '{value}'")

    unit = stripped[-1].lower()
    multiplier = {"s": 1000, "m": 60_000, "h": 3_600_000}.get(unit)
    if multiplier is None:
        raise ValueError(f"Unknown time unit '{unit}' in duration '{value}'")

    try:
        amount = float(stripped[:-1])
    except ValueError as exc:
        raise ValueError(f"Invalid duration '{value}'") from exc

    return int(amount * multiplier)


def parse_inputs_json(inputs_json: str) -> dict[str, Any]:
    if not inputs_json.strip():
        return {}

    try:
        parsed = json.loads(inputs_json)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Failed to parse 'inputs' parameter as JSON: {exc}") from exc

    if not isinstance(parsed, dict):
        raise ValueError("'inputs' parameter must decode to a JSON object")
    return parsed


def format_duration(duration_ms: int) -> str:
    total_seconds = max(int(duration_ms / 1000), 0)
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60
    return f"{hours:02d}h {minutes:02d}m {seconds:02d}s"


def is_timed_out(start_monotonic: float, timeout_ms: int) -> bool:
    return (time.monotonic() - start_monotonic) * 1000 >= timeout_ms


def sleep_ms(duration_ms: int) -> None:
    time.sleep(max(duration_ms, 0) / 1000)


def escape_imported_logs(text: str) -> str:
    escaped = re.sub(r"^", "| ", text, flags=re.MULTILINE)
    return re.sub(r"##\[([^\]]+)\]", r"##<\1>", escaped)


def format_logs_as_output(logs_by_job: dict[str, str]) -> str:
    lines: list[str] = []
    for job_name, logs in logs_by_job.items():
        for line in logs.splitlines():
            lines.append(f"{job_name} | {line}")
    return "\n".join(lines)


def format_logs_as_json_output(logs_by_job: dict[str, str]) -> str:
    result: dict[str, list[dict[str, str]]] = {}
    for job_name, logs in logs_by_job.items():
        entries: list[dict[str, str]] = []
        for line in logs.splitlines():
            if not line:
                continue
            match = TIMESTAMPED_LOG_LINE.match(line)
            if match:
                entries.append({"datetime": match.group(1), "message": match.group(2)})
            else:
                entries.append({"datetime": "", "message": line})
        result[job_name] = entries
    return json.dumps(result)


def select_workflow_run(runs: list[dict[str, Any]], run_name: str) -> dict[str, Any]:
    filtered = runs
    if run_name:
        filtered = [run for run in runs if str(run.get("name", "")) == run_name]

    if not filtered:
        raise RuntimeError("Run not found")

    if len(filtered) > 1:
        print(f"::warning::Found {len(filtered)} workflow runs. Using the latest one.")
        debug("Filtered workflow runs", filtered)

    return filtered[0]


def now_utc_iso_no_millis() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def download_text(url: str, token: str, user_agent: str) -> str:
    request = urllib.request.Request(
        url,
        method="GET",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": user_agent,
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as err:
        detail = err.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"GitHub API GET {url} failed: {err.code} {detail}") from err


@dataclass
class Args:
    token: str
    workflow_ref: str
    ref: str
    owner: str
    repo: str
    inputs: dict[str, Any]
    run_name: str
    display_workflow_url: bool
    display_workflow_url_interval_ms: int
    display_workflow_url_timeout_ms: int
    wait_for_completion: bool
    wait_for_completion_timeout_ms: int
    wait_for_completion_interval_ms: int
    workflow_logs_mode: str


def get_args() -> Args:
    token = os.getenv("ACTION_TOKEN", "").strip()
    workflow_ref = os.getenv("ACTION_WORKFLOW", "").strip()
    ref = os.getenv("ACTION_REF", "").strip() or os.getenv("GITHUB_REF", "").strip()
    repo_input = os.getenv("ACTION_REPO", "").strip() or os.getenv("GITHUB_REPOSITORY", "").strip()
    run_name = os.getenv("ACTION_RUN_NAME", "").strip()

    if not token:
        raise ValueError("Missing required input 'token'")
    if not workflow_ref:
        raise ValueError("Missing required input 'workflow'")
    if not ref:
        raise ValueError("Missing workflow ref; set 'ref' input or ensure GITHUB_REF is present")
    if "/" not in repo_input:
        raise ValueError(f"Invalid repo value '{repo_input}'. Expected owner/name")

    owner, repo = repo_input.split("/", 1)

    return Args(
        token=token,
        workflow_ref=workflow_ref,
        ref=ref,
        owner=owner,
        repo=repo,
        inputs=parse_inputs_json(os.getenv("ACTION_INPUTS_JSON", "")),
        run_name=run_name,
        display_workflow_url=parse_bool(os.getenv("ACTION_DISPLAY_WORKFLOW_RUN_URL", ""), default=True),
        display_workflow_url_interval_ms=to_milliseconds(
            os.getenv("ACTION_DISPLAY_WORKFLOW_RUN_URL_INTERVAL", "1m")
        ),
        display_workflow_url_timeout_ms=to_milliseconds(
            os.getenv("ACTION_DISPLAY_WORKFLOW_RUN_URL_TIMEOUT", "10m")
        ),
        wait_for_completion=parse_bool(os.getenv("ACTION_WAIT_FOR_COMPLETION", ""), default=True),
        wait_for_completion_timeout_ms=to_milliseconds(
            os.getenv("ACTION_WAIT_FOR_COMPLETION_TIMEOUT", "1h")
        ),
        wait_for_completion_interval_ms=to_milliseconds(
            os.getenv("ACTION_WAIT_FOR_COMPLETION_INTERVAL", "1m")
        ),
        workflow_logs_mode=os.getenv("ACTION_WORKFLOW_LOGS", "ignore").strip() or "ignore",
    )


class WorkflowHandler:
    def __init__(self, args: Args) -> None:
        self.args = args
        self.api_base = os.getenv("GITHUB_API_URL", "https://api.github.com").rstrip("/")
        self.user_agent = "solace-public-workflows/workflow-dispatch-and-wait"
        self.workflow_id: int | str | None = None
        self.workflow_run_id: int | None = None
        self.trigger_date: str = ""

    def trigger_workflow(self) -> None:
        workflow_id = self.get_workflow_id()
        self.trigger_date = now_utc_iso_no_millis()
        url = (
            f"{self.api_base}/repos/{self.args.owner}/{self.args.repo}/actions/workflows/"
            f"{workflow_id}/dispatches"
        )
        payload = {"ref": self.args.ref, "inputs": self.args.inputs}
        github_api("POST", url, self.args.token, payload, user_agent=self.user_agent)
        debug("Workflow dispatch payload", payload)

    def get_workflow_id(self) -> int | str:
        if self.workflow_id is not None:
            return self.workflow_id

        if re.fullmatch(r".+\.ya?ml", self.args.workflow_ref):
            self.workflow_id = self.args.workflow_ref
            return self.workflow_id

        url = f"{self.api_base}/repos/{self.args.owner}/{self.args.repo}/actions/workflows?per_page=100"
        payload = github_api("GET", url, self.args.token, user_agent=self.user_agent)
        workflows = payload.get("workflows", []) if isinstance(payload, dict) else []
        debug("List workflows", workflows)

        for workflow in workflows:
            workflow_name = str(workflow.get("name", ""))
            workflow_id = str(workflow.get("id", ""))
            if workflow_name == self.args.workflow_ref or workflow_id == self.args.workflow_ref:
                self.workflow_id = int(workflow["id"])
                return self.workflow_id

        raise RuntimeError(
            f"Unable to find workflow '{self.args.workflow_ref}' in {self.args.owner}/{self.args.repo}"
        )

    def list_workflow_runs(self) -> list[dict[str, Any]]:
        workflow_id = self.get_workflow_id()
        params = urllib.parse.urlencode(
            {
                "event": "workflow_dispatch",
                "created": f">={self.trigger_date}",
                "per_page": 100,
            }
        )
        url = (
            f"{self.api_base}/repos/{self.args.owner}/{self.args.repo}/actions/workflows/"
            f"{workflow_id}/runs?{params}"
        )
        payload = github_api("GET", url, self.args.token, user_agent=self.user_agent)
        runs = payload.get("workflow_runs", []) if isinstance(payload, dict) else []
        debug("List workflow runs", runs)
        return runs

    def get_workflow_run_id(self) -> int:
        if self.workflow_run_id is not None:
            return self.workflow_run_id

        selected = select_workflow_run(self.list_workflow_runs(), self.args.run_name)
        self.workflow_run_id = int(selected["id"])
        return self.workflow_run_id

    def get_workflow_run_status(self) -> dict[str, Any]:
        run_id = self.get_workflow_run_id()
        url = f"{self.api_base}/repos/{self.args.owner}/{self.args.repo}/actions/runs/{run_id}"
        payload = github_api("GET", url, self.args.token, user_agent=self.user_agent)
        debug("Workflow run status", payload)

        status = str(payload.get("status") or "queued")
        conclusion = str(payload.get("conclusion") or "neutral")
        html_url = str(payload.get("html_url") or "")

        return {
            "id": run_id,
            "url": html_url,
            "status": status,
            "conclusion": conclusion,
        }

    def list_jobs_for_workflow_run(self, run_id: int) -> list[dict[str, Any]]:
        url = (
            f"{self.api_base}/repos/{self.args.owner}/{self.args.repo}/actions/runs/{run_id}/jobs"
            "?per_page=100"
        )
        payload = github_api("GET", url, self.args.token, user_agent=self.user_agent)
        jobs = payload.get("jobs", []) if isinstance(payload, dict) else []
        debug("Workflow run jobs", jobs)
        return jobs

    def download_job_logs(self, job_id: int) -> str:
        url = f"{self.api_base}/repos/{self.args.owner}/{self.args.repo}/actions/jobs/{job_id}/logs"
        return download_text(url, self.args.token, self.user_agent)


def get_follow_url(
    workflow_handler: WorkflowHandler,
    interval_ms: int,
    timeout_ms: int,
) -> str:
    start = time.monotonic()
    while not is_timed_out(start, timeout_ms):
        sleep_ms(interval_ms)
        try:
            result = workflow_handler.get_workflow_run_status()
            if result["id"]:
                write_output("workflow-id", str(result["id"]))
            if result["url"]:
                return str(result["url"])
        except Exception as exc:
            debug(f"Failed to get workflow URL: {exc}")
    return ""


def wait_for_completion_or_timeout(
    workflow_handler: WorkflowHandler,
    interval_ms: int,
    timeout_ms: int,
) -> tuple[dict[str, Any] | None, float]:
    start = time.monotonic()
    result: dict[str, Any] | None = None

    while not is_timed_out(start, timeout_ms):
        sleep_ms(interval_ms)
        try:
            result = workflow_handler.get_workflow_run_status()
            if result["id"]:
                write_output("workflow-id", str(result["id"]))
            if result["url"]:
                write_output("workflow-url", str(result["url"]))

            status = str(result["status"])
            debug(
                f"Workflow is running for {format_duration(int((time.monotonic() - start) * 1000))}. "
                f"Current status={status}"
            )
            if status == WORKFLOW_RUN_STATUS_COMPLETED:
                return result, start
        except Exception as exc:
            print(f"::warning::Failed to get workflow status: {exc}")

    return result, start


def handle_logs(args: Args, workflow_handler: WorkflowHandler) -> None:
    if args.workflow_logs_mode not in {"print", "output", "json-output"}:
        return

    try:
        run_id = workflow_handler.get_workflow_run_id()
        jobs = workflow_handler.list_jobs_for_workflow_run(run_id)
    except Exception as exc:
        print(f"::error::Failed to list jobs for triggered workflow. Cause: {exc}")
        return

    logs_by_job: dict[str, str] = {}
    for job in jobs:
        job_name = str(job.get("name") or f"job-{job.get('id')}")
        job_id = int(job["id"])
        try:
            logs_by_job[job_name] = workflow_handler.download_job_logs(job_id)
        except Exception as exc:
            print(f"::warning::Failed to download logs for job '{job_name}'. Cause: {exc}")

    if args.workflow_logs_mode == "print":
        for job_name, logs in logs_by_job.items():
            print(f"::group::Logs of job '{job_name}'")
            print(escape_imported_logs(logs))
            print("::endgroup::")
        return

    if args.workflow_logs_mode == "output":
        write_output("workflow-logs", format_logs_as_output(logs_by_job))
        return

    if args.workflow_logs_mode == "json-output":
        write_output("workflow-logs", format_logs_as_json_output(logs_by_job))


def compute_conclusion(
    start_monotonic: float,
    timeout_ms: int,
    result: dict[str, Any] | None,
) -> int:
    if is_timed_out(start_monotonic, timeout_ms):
        print("Workflow wait timed out")
        write_output("workflow-conclusion", "timed_out")
        raise RuntimeError("Workflow run has failed due to timeout")

    conclusion = str((result or {}).get("conclusion") or "neutral")
    print(f"Workflow completed with conclusion={conclusion}")
    write_output("workflow-conclusion", conclusion)

    if conclusion == "failure":
        raise RuntimeError("Workflow run has failed")
    if conclusion == "cancelled":
        raise RuntimeError("Workflow run was cancelled")
    if conclusion == "timed_out":
        raise RuntimeError("Workflow run has failed due to timeout")
    return 0


def main() -> int:
    try:
        args = get_args()
        workflow_handler = WorkflowHandler(args)

        workflow_handler.trigger_workflow()
        print("Workflow triggered 🚀")

        if args.display_workflow_url:
            url = get_follow_url(
                workflow_handler,
                args.display_workflow_url_interval_ms,
                args.display_workflow_url_timeout_ms,
            )
            if url:
                print(f"You can follow the running workflow here: {url}")
                write_output("workflow-url", url)
            else:
                print("Workflow URL could not be resolved before timeout.")

        if not args.wait_for_completion:
            return 0

        print("Waiting for workflow completion")
        result, start = wait_for_completion_or_timeout(
            workflow_handler,
            args.wait_for_completion_interval_ms,
            args.wait_for_completion_timeout_ms,
        )

        handle_logs(args, workflow_handler)

        if result:
            write_output("workflow-id", str(result["id"]))
            write_output("workflow-url", str(result["url"]))

        return compute_conclusion(start, args.wait_for_completion_timeout_ms, result)
    except Exception as exc:
        print(f"::error::{exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
