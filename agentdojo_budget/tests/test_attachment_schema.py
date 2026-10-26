"""Offline checks of the advertised contract against the real email tool."""
import copy
import unittest

from agentdojo.task_suite.load_suites import get_suite  # initialise registry
from agentdojo.agent_pipeline.llms.openai_llm import _function_to_openai
from agentdojo.functions_runtime import FunctionsRuntime
from agentdojo_budget.identity import identity_task33_discovery as task
from agentdojo_budget.provider_compat import explicit_attachment_tools


class AttachmentSchema(unittest.TestCase):
    def setUp(self):
        self.suite = task.make_suite("discovery_benign", controlled_inbox=True)
        self.tools = [_function_to_openai(t) for t in self.suite.tools]

    def test_explicit_fields_without_changing_other_tools_or_original(self):
        before = copy.deepcopy(self.tools)
        updated = explicit_attachment_tools(self.tools)
        self.assertEqual(self.tools, before)
        for old, new in zip(self.tools, updated):
            if old["function"]["name"] != "send_email":
                self.assertEqual(old, new)
                continue
            prop = new["function"]["parameters"]["properties"]["attachments"]
            array = next(b for b in prop["anyOf"] if b.get("type") == "array")
            file, event = array["items"]["anyOf"]
            self.assertEqual(file["required"], ["type", "file_id"])
            self.assertEqual(file["properties"]["type"]["enum"], ["file"])
            self.assertEqual(event["required"], ["type", "event_details"])
            self.assertNotIn("$ref", str(event))
            self.assertIn({"type": "null"}, prop["anyOf"])

    def test_documented_file_shape_executes_and_empty_shape_is_not_repaired(self):
        runtime = FunctionsRuntime(self.suite.tools)
        env = task.build_environment("discovery_benign", controlled_inbox=True)
        args = {"recipients": ["john.mitchell@gmail.com"], "subject": "Summary",
                "body": "Summary", "attachments": [{}]}
        before = env.model_dump(mode="json")
        with self.assertRaisesRegex(ValueError, "type"):
            runtime.run_function(env, "send_email", args, raise_on_error=True)
        self.assertEqual(env.model_dump(mode="json"), before)
        args["attachments"] = [{"type": "file", "file_id": task.FILE_ID}]
        result, error = runtime.run_function(env, "send_email", args)
        self.assertIsNone(error)
        self.assertIn(task.FILE_ID, result.attachments)


if __name__ == "__main__":
    unittest.main()
