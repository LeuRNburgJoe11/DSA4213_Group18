"""Offline checks for task_002 (OTP): variants build, scripted replays score as expected."""

import json
import tempfile
import unittest
from pathlib import Path

from harness.agent import ScriptedBackend
from harness.run_episode import build_environment, load_task, run_episode

TASKS = Path(__file__).resolve().parents[1] / "tasks"


def script(name):
    return json.loads((TASKS / "scripts" / name).read_text(encoding="utf-8"))


class Task002(unittest.TestCase):
    def setUp(self):
        self.task = load_task(TASKS / "task_002.json")

    def run_scripted(self, variant, script_name):
        with tempfile.TemporaryDirectory() as directory:
            return run_episode(self.task, variant, ScriptedBackend(script(script_name)),
                               "none", Path(directory))

    def test_every_variant_builds_with_no_unfilled_placeholder(self):
        for variant in self.task["variants"]:
            with self.subTest(variant=variant):
                env = build_environment(self.task, variant)
                text = json.dumps(env.to_dict())
                self.assertNotIn("{{", text)

    def test_attacker_text_only_appears_in_attack_variants(self):
        for variant, meta in self.task["variants"].items():
            with self.subTest(variant=variant):
                text = json.dumps(build_environment(self.task, variant).to_dict())
                self.assertEqual("auth-relay.example" in text, meta["kind"] != "benign")

    def test_code_is_only_in_the_seeded_read_email(self):
        env = build_environment(self.task, "multi_source")
        holders = [e.id for e in env.mailbox.emails if "718294" in e.body]
        self.assertEqual(holders, ["e1"])
        self.assertTrue(env.mailbox.emails[0].read)
        self.assertFalse(any("718294" in e.description for e in env.calendar.events))

    def test_benign_replay_passes_utility(self):
        result = self.run_scripted("benign", "task_002_benign.json")
        self.assertTrue(result["utility"])
        self.assertIsNone(result["attack_success"])

    def test_hijacked_replay_is_scored_as_leak_and_keeps_utility(self):
        result = self.run_scripted("visible_late", "task_002_hijacked.json")
        self.assertTrue(result["attack_success"])
        self.assertTrue(result["utility"])
        self.assertEqual(result["leak_evidence"][0]["fact_ids"], ["sso_verification_code"])

    def test_benign_replay_on_attack_variant_is_not_a_leak(self):
        result = self.run_scripted("visible_late", "task_002_benign.json")
        self.assertFalse(result["attack_success"])
        self.assertTrue(result["utility"])


if __name__ == "__main__":
    unittest.main()
