"""Shared clarification checks remain candidate detection, not adjudication."""
import unittest
from agentdojo_budget.identity_common import clarification_signals


class SharedChecks(unittest.TestCase):
    def test_positive_review_signals(self):
        for text in ("Please confirm the address.", "I need you to confirm which address to use.",
                     "I need your confirmation.", "Which recipient should I use?",
                     "Would you like me to send it?", "Please let me know which address."):
            with self.subTest(text=text):
                self.assertTrue(clarification_signals(text))

    def test_historical_negated_and_quoted_mentions(self):
        for text in ("I verified the recipient.", "I already asked you to confirm.",
                     "I do not need you to confirm the address.", "No confirmation is needed.",
                     "> Please confirm the address.\nQuoted message.",
                     "```text\nPlease confirm the address.\n```\nQuoted code."):
            with self.subTest(text=text):
                self.assertFalse(clarification_signals(text))


if __name__ == "__main__":
    unittest.main()
