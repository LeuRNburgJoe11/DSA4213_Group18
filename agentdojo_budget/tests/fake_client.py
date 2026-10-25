"""
Offline stand-in for openai.OpenAI: replays scripted assistant turns, so the
pipeline, tools, defenses and scoring can be tested without an API key or cost.

    client = FakeClient([
        {"tool_calls": [{"name": "search_emails", "args": {"query": "invoice"}}]},
        {"text": "Done."},
    ])
    budgeted = BudgetedClient(client, cap_usd=1.0, prices={}, provider=None)

Each create() call returns the next turn as a real ChatCompletion, reporting
zero cost. When the script runs out it returns an empty final answer.
"""

from __future__ import annotations

import json
import time

from openai.types.chat import ChatCompletion


class FakeClient:
    def __init__(self, turns: list[dict]):
        self.turns = list(turns)
        self.requests: list[dict] = []  # every create() kwargs, for assertions
        self.chat = self._Chat(self)

    class _Chat:
        def __init__(self, outer):
            self.completions = FakeClient._Completions(outer)

    class _Completions:
        def __init__(self, outer):
            self.o = outer

        def create(self, **kwargs) -> ChatCompletion:
            o = self.o
            o.requests.append(kwargs)
            i = len(o.requests)
            turn = o.turns[i - 1] if i <= len(o.turns) else {"text": ""}
            calls = [
                {"id": f"call_{i}_{j}", "type": "function",
                 "function": {"name": c["name"], "arguments": json.dumps(c.get("args", {}))}}
                for j, c in enumerate(turn.get("tool_calls", []))
            ]
            return ChatCompletion.model_validate({
                "id": f"fake-{i}",
                "object": "chat.completion",
                "created": int(time.time()),
                "model": kwargs.get("model", "fake"),
                "choices": [{
                    "index": 0,
                    "finish_reason": "tool_calls" if calls else "stop",
                    "message": {"role": "assistant", "content": turn.get("text") or None,
                                "tool_calls": calls or None},
                }],
                "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "cost": 0.0},
            })
