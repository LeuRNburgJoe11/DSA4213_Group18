"""Offline checks for the experiment pipeline: freeze, resume, scoring and outcome labels."""

import json
import tempfile
import unittest
from pathlib import Path

from harness import experiment as E

CONFIG = Path(__file__).resolve().parents[1] / "experiments" / "main.json"


class Pipeline(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        config = json.loads(CONFIG.read_text(encoding="utf-8"))
        config.update(defenses=["none", "privilege_separation"], trials=1)
        config["tasks"] = config["tasks"][:1]
        self.config = self.tmp / "cfg.json"
        self.config.write_text(json.dumps(config), encoding="utf-8")

    def run_cli(self, *args):
        return E.main([*args, "--config", str(self.config), "--run-id", "r",
                       "--out", str(self.tmp), "--offline", "--skip-validation"])

    def records(self):
        return list(E.load_records(self.tmp / "r").values())

    def test_runs_resume_and_score(self):
        self.run_cli("benign")
        self.run_cli("security")
        self.assertEqual(len(self.records()), 2 + 2 * 4)
        self.run_cli("security")  # resume: nothing new
        self.assertEqual(len(self.records()), 10)
        self.run_cli("score")
        self.assertTrue((self.tmp / "r" / "episodes.csv").exists())
        rec = next(r for r in self.records() if r["variant"] == "multi_source")
        self.assertEqual((rec["k"], rec["coordination"]), (3, "redundant"))
        self.assertTrue(len({r["config_id"] for r in self.records()}) == 1)

    def test_changed_config_refuses_old_run_id(self):
        self.run_cli("freeze")
        config = json.loads(self.config.read_text(encoding="utf-8"))
        config["trials"] = 2
        self.config.write_text(json.dumps(config), encoding="utf-8")
        with self.assertRaises(SystemExit):
            self.run_cli("freeze")


class Labels(unittest.TestCase):
    def label(self, **kw):
        base = {"termination": "completed", "attack_success": False, "utility": False,
                "side_effect_calls": 0, "final_text": ""}
        return E.label_episode({**base, **kw})["outcome"]

    def test_labels(self):
        self.assertEqual(self.label(attack_success=True), "attack_executed")
        self.assertEqual(self.label(utility=True), "attack_refused_task_completed")
        self.assertEqual(self.label(utility=True, attack_success=None), "task_completed")
        self.assertEqual(self.label(final_text="Which address should I use for Brightline?"),
                         "clarification_requested")
        self.assertEqual(self.label(final_text="I can't send that information."), "episode_refused")
        self.assertEqual(self.label(side_effect_calls=1, final_text="Done."), "task_failed")
        self.assertEqual(self.label(termination="error"), "run_error")
        self.assertEqual(self.label(termination="api_refusal"), "episode_refused")


if __name__ == "__main__":
    unittest.main()
