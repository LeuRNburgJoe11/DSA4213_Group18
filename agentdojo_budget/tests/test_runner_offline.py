"""
Offline tests for dojo_budget.py: no API key, no network, no spend.

A scripted fake agent replays AgentDojo's own ground-truth tool calls, so the
correct labels are known in advance. Everything else is the real runner:
build_pipeline, run_grid, AgentDojo's scoring and collect_results. Only the
OpenRouter client and the price fetch are swapped out, and the ledger and
traces go to a temp folder.

    .venv/bin/python -m unittest discover -s agentdojo_budget -p 'test_*.py' -v      (from the repo root)
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import dojo_budget as d
from tests.fake_client import FakeClient

USER, INJ = "user_task_4", "injection_task_2"


def suite():
    from agentdojo.task_suite.load_suites import get_suite

    return get_suite(d.BENCHMARK_VERSION, d.SUITE_NAME)


def gt_turn(task) -> dict:
    """One assistant turn that makes all of a task's ground-truth tool calls."""
    env = suite().load_and_inject_default_environment({})
    return {"tool_calls": [{"name": c.function, "args": dict(c.args)} for c in task.ground_truth(env)]}


def answer() -> dict:
    return {"text": suite().get_user_task_by_id(USER).GROUND_TRUTH_OUTPUT}


class OfflineRunner(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        for name, value in {"LEDGER": self.tmp / "ledger.jsonl", "RUNS": self.tmp / "runs",
                            "fetch_prices": lambda: {}}.items():
            patcher = mock.patch.object(d, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def run_scripted(self, turns: list[dict], cap: float = 1.0) -> dict:
        """Run one benign + one attacked episode on the fake agent; return rows by injection task."""
        fake = FakeClient(turns)
        client = d.BudgetedClient(fake, cap, {}, provider=None)
        sample = d.Sample([USER], [INJ])
        with mock.patch.object(d, "make_client", lambda *a: client):
            d.run_grid(["gemini"], ["none"], 1, sample, cap, 10, phase="test")
        self.fake = fake
        return {r["injection_task"]: r for r in d.collect_results(["gemini"], ["none"], 1, sample)}

    def test_correct_agent_resists_attack(self):
        user = gt_turn(suite().get_user_task_by_id(USER))
        rows = self.run_scripted([user, answer(), user, answer()])
        self.assertEqual(rows["none"]["utility"], 1)
        self.assertEqual((rows[INJ]["utility"], rows[INJ]["attack_success"]), (1, 0))

    def test_hijacked_agent_is_scored_as_attack(self):
        s = suite()
        user, inj = gt_turn(s.get_user_task_by_id(USER)), gt_turn(s.get_injection_task_by_id(INJ))
        rows = self.run_scripted([user, answer(), user, inj, answer()])
        # Utility is 0 even though the user task was done: AgentDojo's utility is strict,
        # and the attacker's extra calendar event is an unrequested change.
        self.assertEqual((rows[INJ]["utility"], rows[INJ]["attack_success"]), (0, 1))

    def test_idle_agent_fails_utility(self):
        rows = self.run_scripted([{"text": "Done."}, {"text": "Done."}])
        self.assertEqual(rows["none"]["utility"], 0)
        self.assertEqual(rows[INJ]["attack_success"], 0)

    def test_ledger_is_tagged_and_free(self):
        self.run_scripted([{"text": "Done."}, {"text": "Done."}])
        entries = [json.loads(line) for line in d.LEDGER.read_text().splitlines()]
        self.assertEqual({e["injection_task"] for e in entries}, {"none", INJ})
        self.assertTrue(all(e["cost"] == 0 and e["phase"] == "test" for e in entries))

    def test_budget_cap_blocks_calls(self):
        rows = self.run_scripted([{"text": "Done."}], cap=0.0)
        self.assertEqual(self.fake.requests, [])  # stopped before the first API call
        self.assertEqual(rows, {})

    def test_resume_skips_finished_episodes(self):
        self.run_scripted([{"text": "Done."}, {"text": "Done."}])
        self.run_scripted([{"text": "Done."}, {"text": "Done."}])
        self.assertEqual(self.fake.requests, [])


class Reproducible(unittest.TestCase):
    """Rule 5: seed 4213 always gives these samples. If this fails, results are not comparable."""

    def test_rq1_sample_is_fixed(self):
        s = d.make_sample(5, 3, 4213)
        self.assertEqual(s.user_tasks, ["user_task_4", "user_task_5", "user_task_27", "user_task_29", "user_task_38"])
        self.assertEqual(s.injection_tasks, ["injection_task_2", "injection_task_5", "injection_task_13"])

    def test_pilot_sample_is_fixed(self):
        s = d.make_sample(2, 1, 4213)
        self.assertEqual((s.user_tasks, s.injection_tasks), (["user_task_29", "user_task_38"], ["injection_task_13"]))


if __name__ == "__main__":
    unittest.main()
