"""Runner contract: only current RQ2 variants, and validation before networking."""
from contextlib import redirect_stderr
from io import StringIO
import unittest
from unittest.mock import patch
from agentdojo_budget import run_identity_pilot as runner


class RunnerTests(unittest.TestCase):
    def test_only_three_active_variants(self):
        self.assertEqual(set(runner.TASKS), {"25", "33-discovery", "33-change"})
        for name, module in runner.TASKS.items():
            self.assertIn(runner.default_condition_set(name), module.CONDITION_SETS)
            self.assertEqual(runner.execution_limits(name), (20, 21))
        self.assertEqual(runner.default_inbox_exposure("33-change", "change-eight"), "required")

    def test_invalid_and_legacy_options_stop_before_network(self):
        for args in (("--task", "33"),
                     ("--task", "25", "--controlled-inbox", "--condition-set", "change-eight"),
                     ("--task", "33-change", "--controlled-inbox", "--conditions", "unknown")):
            with self.subTest(args=args), patch("sys.argv", ["pilot", *args]), \
                    patch.object(runner, "load_dotenv") as load_env, redirect_stderr(StringIO()):
                with self.assertRaises(SystemExit) as result:
                    runner.main()
                self.assertEqual(result.exception.code, 2)
                load_env.assert_not_called()


if __name__ == "__main__":
    unittest.main()
