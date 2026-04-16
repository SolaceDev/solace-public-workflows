#!/usr/bin/env python3
"""Unit tests for workflow-dispatch-and-wait helpers."""

from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "run.py"
SPEC = importlib.util.spec_from_file_location("workflow_dispatch_and_wait_run", MODULE_PATH)
assert SPEC is not None
assert SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class TestWorkflowDispatchAndWaitHelpers(unittest.TestCase):
    def test_to_milliseconds_supports_seconds_minutes_and_hours(self) -> None:
        self.assertEqual(MODULE.to_milliseconds("30s"), 30_000)
        self.assertEqual(MODULE.to_milliseconds("1.5m"), 90_000)
        self.assertEqual(MODULE.to_milliseconds("2h"), 7_200_000)

    def test_parse_inputs_json_requires_object(self) -> None:
        self.assertEqual(MODULE.parse_inputs_json(""), {})
        self.assertEqual(MODULE.parse_inputs_json('{"name":"value"}'), {"name": "value"})

        with self.assertRaises(ValueError):
            MODULE.parse_inputs_json("[1,2,3]")

        with self.assertRaises(ValueError):
            MODULE.parse_inputs_json("{not-json}")

    def test_select_workflow_run_filters_by_run_name(self) -> None:
        runs = [
            {"id": 3, "name": "other"},
            {"id": 2, "name": "target"},
        ]

        selected = MODULE.select_workflow_run(runs, "target")
        self.assertEqual(selected["id"], 2)

    def test_format_logs_outputs(self) -> None:
        logs_by_job = {
            "build": (
                "2026-03-09T12:34:56.1234567Z First line\n"
                "2026-03-09T12:34:57.1234567Z Second line"
            ),
        }

        output_logs = MODULE.format_logs_as_output(logs_by_job)
        self.assertIn("build | 2026-03-09T12:34:56.1234567Z First line", output_logs)

        json_logs = json.loads(MODULE.format_logs_as_json_output(logs_by_job))
        self.assertEqual(
            json_logs,
            {
                "build": [
                    {"datetime": "2026-03-09T12:34:56.1234567Z", "message": "First line"},
                    {"datetime": "2026-03-09T12:34:57.1234567Z", "message": "Second line"},
                ]
            },
        )


if __name__ == "__main__":
    unittest.main()
