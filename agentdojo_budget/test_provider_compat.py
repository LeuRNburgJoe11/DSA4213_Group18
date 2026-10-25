import unittest
from agentdojo_budget.provider_compat import ReasoningMetadata, completion_failure
from agentdojo_budget import identity_task33_discovery as discovery


class ProviderCompatibilityTests(unittest.TestCase):
    def test_provider_finish_classification(self):
        cases = [("error", "MALFORMED_FUNCTION_CALL", "malformed_function_call"),
                 ("error", "OTHER", "provider_completion_error"),
                 ("length", "MAX_TOKENS", "model_output_limit"),
                 ("content_filter", None, "provider_content_filter")]
        for finish, native, expected in cases:
            failure = completion_failure({"choices": [{"finish_reason": finish, "native_finish_reason": native}]})
            self.assertEqual(failure["failure_reason"], expected)
            env = discovery.build_environment("discovery_benign")
            r = discovery.score_episode("discovery_benign", env, env, "", termination=expected)
            self.assertEqual(r["outcome"], "incomplete")
            self.assertFalse(r["task_completed"])
        for finish in ("stop", "tool_calls"):
            self.assertIsNone(completion_failure({"choices": [{"finish_reason": finish}]}))
        self.assertEqual(completion_failure({"choices": []})["failure_reason"], "empty_provider_response")

    def test_reasoning_replayed_unchanged_only_for_matching_tool_turn(self):
        cache = ReasoningMetadata()
        details = [{"type": "reasoning.encrypted", "data": "opaque-test-data", "index": 0}]
        calls = [{"id": "call_1", "type": "function", "function": {"name": "list_files", "arguments": "{}"}}]
        response = {"choices": [{"message": {"tool_calls": calls, "reasoning_details": details}}]}
        cache.remember(response)
        messages = [{"role": "assistant", "content": None, "tool_calls": calls},
                    {"role": "tool", "tool_call_id": "call_1", "content": "File19"}]
        restored = cache.restore(messages)
        self.assertEqual(restored[0]["reasoning_details"], details)
        self.assertNotIn("reasoning_details", messages[0])
        self.assertEqual(restored[0]["tool_calls"], calls)
        self.assertEqual(restored[1], messages[1])
        self.assertNotIn("reasoning_details", ReasoningMetadata().restore(messages)[0])
        unmatched = [{"role": "assistant", "tool_calls": [{**calls[0], "id": "other"}]}]
        self.assertNotIn("reasoning_details", cache.restore(unmatched)[0])


if __name__ == "__main__":
    unittest.main()
