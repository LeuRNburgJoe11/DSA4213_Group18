"""Offline integration test for the OpenRouter message adapter."""

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace as NS

from harness.agent import OpenRouterBackend
from harness.run_episode import load_task, run_episode


def response(calls=(), text="", reason="tool_calls"):
    tool_calls = [NS(id=f"call_{i}_{name}", function=NS(name=name,
                  arguments=json.dumps(args))) for i, (name, args) in enumerate(calls)]
    return NS(choices=[NS(finish_reason=reason,
                          message=NS(content=text, tool_calls=tool_calls))],
              usage=NS(prompt_tokens=100, completion_tokens=20))


class FakeCompletions:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.requests = []

    def create(self, **kwargs):
        self.requests.append(kwargs)
        return next(self.responses)


class OpenRouterBackendTests(unittest.TestCase):
    def test_full_benign_episode_and_tool_history(self):
        task = load_task(Path(__file__).resolve().parents[1] / "tasks/task_001.json")
        replies = [
            response([("read_emails", {"unread_only": True})]),
            response([("read_calendar", {"date": "2026-10-07"})]),
            response([
                ("create_event", {"title": "Design review", "start": "2026-10-07T14:00:00+08:00",
                                  "end": "2026-10-07T15:00:00+08:00",
                                  "participants": ["daniel.lim@nimbus.example"]}),
                ("send_email", {"to": ["priya.nair@nimbus.example"],
                                "subject": "Inbox summary",
                                "body": "Design review; invoice and timesheet reminders."}),
            ]),
            response(text="Done", reason="stop"),
        ]
        completions = FakeCompletions(replies)
        client = NS(chat=NS(completions=completions))
        backend = OpenRouterBackend("provider/model", client=client)
        with tempfile.TemporaryDirectory() as directory:
            result = run_episode(task, "benign", backend, "none", Path(directory))
        self.assertIsNone(result["error"])
        self.assertEqual(result["termination"], "completed")
        self.assertTrue(result["utility"])
        self.assertEqual(result["usage"], {"input_tokens": 400, "output_tokens": 80})
        request = completions.requests[1]
        self.assertEqual(request["model"], "provider/model")
        self.assertEqual(request["tools"][0]["type"], "function")
        self.assertEqual(request["messages"][-2]["role"], "assistant")
        self.assertEqual(request["messages"][-1]["role"], "tool")
        self.assertEqual(request["messages"][-1]["tool_call_id"], "call_0_read_emails")
        final_request = completions.requests[-1]
        self.assertEqual([m["role"] for m in final_request["messages"][-3:]],
                         ["assistant", "tool", "tool"])

    def test_rejects_non_object_tool_arguments(self):
        completions = FakeCompletions([response([("send_email", ["bad"])])])
        backend = OpenRouterBackend("provider/model", client=NS(chat=NS(completions=completions)))
        with self.assertRaisesRegex(ValueError, "JSON object"):
            backend.complete("system", [{"role": "user", "content": "hello"}], [])


if __name__ == "__main__":
    unittest.main()
