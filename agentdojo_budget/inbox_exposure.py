"""Experiment-controlled retrieval before the first model decision."""
from agentdojo.agent_pipeline.base_pipeline_element import BasePipelineElement
from agentdojo.agent_pipeline.tool_execution import ToolsExecutor
from agentdojo.functions_runtime import FunctionCall


class RequiredInboxExposure(BasePipelineElement):
    """Execute a fixed inbox read; retain external content as a tool result.

    This is harness-scheduled retrieval, not an autonomous model-selected call.
    Insert after SystemMessage/InitQuery and before the first LLM element.
    """

    def query(self, query, runtime, env, messages=(), extra_args=None):
        if not messages or messages[-1]["role"] != "user":
            raise ValueError("Required inbox exposure must precede the first model turn.")
        call = FunctionCall(function="get_received_emails", args={}, id="required_inbox_read")
        seeded = [*messages, {"role": "assistant", "content": None, "tool_calls": [call]}]
        result = ToolsExecutor().query(query, runtime, env, seeded, extra_args or {})
        if result[3][-1]["role"] != "tool" or result[3][-1].get("error"):
            raise RuntimeError("Required inbox retrieval failed; no model decision permitted.")
        return result
