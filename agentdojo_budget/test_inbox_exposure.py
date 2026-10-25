"""Offline checks that evidence precedes any model decision in both tasks."""
import unittest
import yaml
from agentdojo_budget import identity_task33_discovery, identity_task25_discovery, identity_task33_change
from agentdojo_budget.inbox_exposure import RequiredInboxExposure
from agentdojo.functions_runtime import FunctionsRuntime
from agentdojo.agent_pipeline import AgentPipeline
from agentdojo.agent_pipeline.basic_elements import SystemMessage, InitQuery
from agentdojo.agent_pipeline.base_pipeline_element import BasePipelineElement
from agentdojo_budget.run_identity_pilot import observed_ids


class ExposureTests(unittest.TestCase):
    def test_prompts_do_not_prescribe_identity_decisions(self):
        for module in (identity_task33_discovery, identity_task25_discovery, identity_task33_change):
            for phrase in ("ask me", "independent evidence", "confirm", "other assignments"):
                self.assertNotIn(phrase, module.PROMPT.lower())

    def test_corroboration_changes_only_inbox_for_both_tasks(self):
        pairs = [(identity_task33_discovery, "discovery_ambiguous", "discovery_history"),
                 (identity_task25_discovery, "discovery_ambiguous", "discovery_history"),
                 (identity_task33_change, "change_familiar_standard", "change_legitimate_standard")]
        for module, first, second in pairs:
            a = module.build_environment(first, controlled_inbox=True)
            b = module.build_environment(second, controlled_inbox=True)
            self.assertEqual(a.cloud_drive, b.cloud_drive)
            self.assertEqual(a.calendar, b.calendar)
            self.assertEqual(a.inbox.contact_list, b.inbox.contact_list)

    def test_first_model_input_contains_all_inbox_messages(self):
        for module in (identity_task33_discovery, identity_task25_discovery, identity_task33_change):
            for name in module.CONDITIONS:
                with self.subTest(task=module.__name__, condition=name):
                    env = module.build_environment(name, controlled_inbox=True)
                    pre = env.model_copy(deep=True)
                    suite = module.make_suite(name, controlled_inbox=True)
                    seen = []

                    class InspectModel(BasePipelineElement):
                        def query(self, query, runtime, env, messages=(), extra_args=None):
                            seen.extend(messages)
                            return query, runtime, env, messages, extra_args

                    pipeline = AgentPipeline([SystemMessage("Test system message"), InitQuery(),
                                              RequiredInboxExposure(), InspectModel()])
                    pipeline.query(module.PROMPT, FunctionsRuntime(suite.tools), env)
                    self.assertEqual([m["role"] for m in seen], ["system", "user", "assistant", "tool"])
                    self.assertEqual(set(observed_ids(seen)), {str(e.id_) for e in pre.inbox.received})
                    self.assertEqual(seen[-2]["tool_calls"][0].function, "get_received_emails")
                    content = str(seen[-1]["content"])
                    received = yaml.safe_load(seen[-1]["content"][0]["content"])
                    received_by_id = {str(e["id_"]): e for e in received}
                    for email in pre.inbox.received:
                        self.assertIn(email.sender, content)
                        self.assertEqual(received_by_id[str(email.id_)]["body"], email.body)
                    # Reading the inbox cannot execute a delivery or alter documents.
                    self.assertEqual(env.inbox.emails, pre.inbox.emails)
                    self.assertEqual(env.cloud_drive, pre.cloud_drive)
                    self.assertEqual(env.calendar, pre.calendar)

    def test_failed_retrieval_prevents_model_turn(self):
        env = identity_task25_discovery.build_environment("discovery_benign")
        with self.assertRaisesRegex(RuntimeError, "retrieval failed"):
            RequiredInboxExposure().query("Test", FunctionsRuntime([]), env,
                                         [{"role": "user", "content": []}])


if __name__ == "__main__":
    unittest.main()
