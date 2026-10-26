"""
RQ2/RQ3 runner: the three-model registry, AgentDojo's built-in defences, and run provenance.

Offline only: no API key, no network, no spend. The scripted fake agent replays fixed turns
(tests/fake_client.py) through the runner's own `build_pipeline`.

What each model entry decides (checked here, not live):
  - the OpenRouter provider the request is pinned to
  - the per-token price ceiling the run refuses to exceed
  - whether a `reasoning` setting is sent at all

    .venv/bin/python -m unittest discover -s agentdojo_budget -p 'test_*.py'   (from the repo root)
"""

from __future__ import annotations

import re
import unittest
from contextlib import redirect_stderr
from io import StringIO
from unittest.mock import patch

from agentdojo.task_suite.load_suites import get_suite  # noqa: F401  (import first: registers the suites)
from agentdojo.agent_pipeline import ToolsExecutionLoop, ToolsExecutor
from agentdojo.functions_runtime import FunctionsRuntime

from agentdojo_budget import run_identity_pilot as runner
from agentdojo_budget.defenses.recipient_gate import RecipientGate
from agentdojo_budget.identity import identity_task33_change as t33c
from agentdojo_budget.inbox_exposure import RequiredInboxExposure
from agentdojo_budget.tests.fake_client import FakeClient

A, B = "john.mitchell@gmail.com", "john_mitchell@gmail.com"

GEMINI = "google/gemini-3.8-flash"
SONNET = "anthropic/claude-sonnet-5.5"
GPT6 = "openai/gpt-6-sol"


def per_token(dollars_per_million):
    return f"{dollars_per_million / 1e6:.12f}"


class Registry(unittest.TestCase):
    def test_models_offered(self):
        self.assertEqual(set(runner.MODELS), {"google/gemini-2.5-flash", "google/gemini-3.5-flash", GEMINI, SONNET, GPT6})
        self.assertEqual(runner.MODEL, "google/gemini-2.5-flash")  # the default is unchanged

    def test_each_model_is_pinned_to_its_own_provider(self):
        self.assertEqual(runner.provider_settings(GEMINI)["order"], ["Google AI Studio"])
        self.assertEqual(runner.provider_settings(SONNET)["order"], ["Anthropic"])
        self.assertEqual(runner.provider_settings(GPT6)["order"], ["OpenAI"])
        for model in runner.MODELS:
            with self.subTest(model=model):
                self.assertFalse(runner.provider_settings(model)["allow_fallbacks"])  # no silent re-routing

    def test_reasoning_is_only_sent_where_it_was_designed_for(self):
        self.assertEqual(runner.reasoning_settings(GEMINI), {"effort": "low"})
        self.assertEqual(runner.reasoning_settings("google/gemini-2.5-flash"), {"enabled": False})
        self.assertIsNone(runner.reasoning_settings(SONNET))
        self.assertIsNone(runner.reasoning_settings(GPT6))

    def test_unknown_model_is_rejected(self):
        with self.assertRaises(ValueError):
            runner.provider_settings("anthropic/claude-sonnet-4")

    def test_price_ceilings_accept_the_listed_prices_and_stop_surprises(self):
        listed = {GEMINI: (0.825, 4.125), "google/gemini-3.5-flash": (1.5, 9.0),
                  "google/gemini-2.5-flash": (0.3, 2.5), SONNET: (2.0, 10.0), GPT6: (2.0, 10.0)}
        for model, (prompt, completion) in listed.items():
            with self.subTest(model=model):
                prices = {"prompt": per_token(prompt), "completion": per_token(completion)}
                self.assertTrue(runner.price_within_limits(model, prices))
        # Flash's ceiling does not stretch to a frontier model's price, and vice versa nothing is waved through.
        frontier = {"prompt": per_token(2.0), "completion": per_token(10.0)}
        self.assertFalse(runner.price_within_limits(GEMINI, frontier))
        self.assertFalse(runner.price_within_limits(SONNET, {"prompt": per_token(5.0), "completion": per_token(10.0)}))
        self.assertFalse(runner.price_within_limits(GEMINI, {"prompt": per_token(0.5), "completion": per_token(1.0),
                                                              "request": "0.01"}))

    def test_request_body_for_gemini_is_exactly_what_it_was(self):
        self.assertEqual(runner.request_extra_body(GEMINI), {
            "reasoning": {"effort": "low"}, "usage": {"include": True},
            "provider": {"order": ["Google AI Studio"], "allow_fallbacks": False,
                         "max_price": {"prompt": 1, "completion": 5}}})

    def test_request_body_for_frontier_models_has_no_reasoning_key(self):
        for model, provider in ((SONNET, "Anthropic"), (GPT6, "OpenAI")):
            with self.subTest(model=model):
                body = runner.request_extra_body(model)
                self.assertNotIn("reasoning", body)
                self.assertEqual(body["provider"]["order"], [provider])
                self.assertEqual(body["usage"], {"include": True})


class CommandLine(unittest.TestCase):
    def run_main(self, *args, key=None):
        with patch("sys.argv", ["pilot", *args]), patch.object(runner, "load_dotenv"), \
                patch.object(runner.os, "getenv", return_value=key), redirect_stderr(StringIO()):
            with self.assertRaises(SystemExit) as result:
                runner.main()
        return result.exception.code

    def test_new_models_and_defences_are_accepted_before_any_network_call(self):
        for model in (SONNET, GPT6):
            for defense in ("origin+identity", "spotlighting_with_delimiting"):
                with self.subTest(model=model, defense=defense):
                    code = self.run_main("--task", "33-change", "--controlled-inbox", "--model", model,
                                         "--defense", defense)
                    self.assertEqual(code, "OPENROUTER_API_KEY missing; no requests made.")  # got past argparse

    def test_unlisted_model_exits_with_usage_error(self):
        self.assertEqual(self.run_main("--task", "33-change", "--controlled-inbox",
                                       "--model", "anthropic/claude-sonnet-4"), 2)


class BuiltInDefenses(unittest.TestCase):
    def build(self, defense, required_inbox=False):
        env = t33c.build_environment("change_unsupported_standard", controlled_inbox=True)
        return runner.build_pipeline(FakeClient([]), GEMINI, max_iters=20, required_inbox=required_inbox,
                                     defense=defense, env=env)

    def episode(self, defense, turns):
        env = t33c.build_environment("change_unsupported_standard", controlled_inbox=True)
        pre = env.model_copy(deep=True)
        suite = t33c.make_suite("change_unsupported_standard", controlled_inbox=True)
        fake = FakeClient(turns)
        pipeline, gate = runner.build_pipeline(fake, GEMINI, max_iters=20, required_inbox=False, defense=defense, env=env)
        pipeline.query(t33c.PROMPT, FunctionsRuntime(suite.tools), env)
        return pre, env, fake, gate

    def test_defences_offered(self):
        self.assertEqual(runner.BUILTIN_DEFENSES, ("spotlighting_with_delimiting", "repeat_user_prompt"))
        self.assertEqual(runner.DEFENSES, ("none", "spotlighting_with_delimiting", "repeat_user_prompt",
                                           "origin", "origin+readers", "origin+identity"))

    def test_builtin_defences_do_not_install_the_gate(self):
        for defense in runner.BUILTIN_DEFENSES:
            with self.subTest(defense=defense):
                pipeline, gate = self.build(defense)
                self.assertIsNone(gate)
                loop = next(e for e in pipeline.elements if isinstance(e, ToolsExecutionLoop))
                self.assertTrue(any(isinstance(e, ToolsExecutor) for e in loop.elements))
                self.assertFalse(any(isinstance(e, RecipientGate) for e in loop.elements))
                self.assertEqual(loop.max_iters, 20)

    def test_required_inbox_exposure_still_lands_after_the_prompt(self):
        for defense in runner.BUILTIN_DEFENSES:
            with self.subTest(defense=defense):
                pipeline, _ = self.build(defense, required_inbox=True)
                self.assertIsInstance(pipeline.elements[2], RequiredInboxExposure)

    def test_spotlighting_marks_tool_output_and_tells_the_model_about_it(self):
        _, _, fake, _ = self.episode("spotlighting_with_delimiting",
                                     [{"tool_calls": [{"name": "get_received_emails", "args": {}}]}, {"text": "ok"}])
        messages = fake.requests[-1]["messages"]
        tool = next(m for m in messages if m["role"] == "tool")
        text = tool["content"] if isinstance(tool["content"], str) else "".join(b.get("text", "") for b in tool["content"])
        self.assertTrue(text.startswith("<<") and text.endswith(">>"))
        self.assertIn("<<", str(messages[0]["content"]))

    def test_repeat_user_prompt_repeats_the_request_after_each_tool_result(self):
        _, _, fake, _ = self.episode("repeat_user_prompt",
                                     [{"tool_calls": [{"name": "get_received_emails", "args": {}}]}, {"text": "ok"}])
        self.assertEqual([m["role"] for m in fake.requests[-1]["messages"]][-2:], ["tool", "user"])

    def test_builtin_defences_do_not_check_recipients(self):
        # They harden against injected instructions, not against who the address belongs to.
        turn = {"name": "send_email", "args": {"recipients": [B], "subject": "S", "body": "b",
                                                "attachments": [{"type": "file", "file_id": "19"}]}}
        for defense in runner.BUILTIN_DEFENSES:
            with self.subTest(defense=defense):
                pre, post, _, _ = self.episode(defense, [{"tool_calls": [turn]}, {"text": "sent"}])
                sent = [a for i, e in post.inbox.emails.items() if i not in pre.inbox.emails
                        for a in e.recipients]
                self.assertEqual(sent, [B])

    def test_gate_summary_names_a_builtin_defence_without_decisions(self):
        self.assertEqual(runner.gate_summary("repeat_user_prompt", None),
                         {"defense": "repeat_user_prompt", "gate_decisions": [], "gate_held": 0})


class Provenance(unittest.TestCase):
    def test_commit_and_dirty_flag_are_recorded(self):
        info = runner.git_provenance()
        self.assertRegex(info["commit"], r"^[0-9a-f]{40}$")
        self.assertIsInstance(info["dirty"], bool)

    def test_missing_git_is_recorded_as_unknown_not_an_error(self):
        with patch.object(runner.subprocess, "run", side_effect=OSError("no git")):
            self.assertEqual(runner.git_provenance(), {"commit": None, "dirty": None})

    def test_output_folder_names_say_which_kind_of_defence_ran(self):
        self.assertEqual(runner.defense_tag("none"), "")
        self.assertEqual(runner.defense_tag("origin+identity"), "_gate-origin-identity")
        self.assertEqual(runner.defense_tag("repeat_user_prompt"), "_defense-repeat_user_prompt")


if __name__ == "__main__":
    unittest.main()
