"""Provider response bookkeeping without changing agent decisions."""
from copy import deepcopy


def completion_failure(response):
    choices = response.get("choices") or []
    if not choices:
        return {"failure_reason": "empty_provider_response", "finish_reason": None,
                "native_finish_reason": None}
    choice = choices[0]
    finish, native = choice.get("finish_reason"), choice.get("native_finish_reason")
    if str(native).upper() == "MALFORMED_FUNCTION_CALL":
        reason = "malformed_function_call"
    elif finish == "error":
        reason = "provider_completion_error"
    elif finish == "length":
        reason = "model_output_limit"
    elif finish == "content_filter":
        reason = "provider_content_filter"
    else:
        return None
    return {"failure_reason": reason, "finish_reason": finish, "native_finish_reason": native}


class ReasoningMetadata:
    """Replay opaque reasoning details on the matching assistant tool-call turn.

    AgentDojo's generic OpenAI adapter omits these provider-specific fields.
    One cache per episode; call IDs match data to its original assistant turn.
    """

    def __init__(self):
        self.by_calls = {}

    def remember(self, response):
        for choice in response.get("choices") or []:
            message = choice.get("message") or {}
            calls = message.get("tool_calls") or []
            key = tuple(call["id"] for call in calls)
            if key and message.get("reasoning_details") is not None:
                self.by_calls[key] = deepcopy(message["reasoning_details"])

    def restore(self, messages):
        restored = deepcopy(messages)
        for message in restored:
            if message.get("role") != "assistant":
                continue
            key = tuple(call["id"] for call in message.get("tool_calls") or [])
            if key in self.by_calls:
                message["reasoning_details"] = deepcopy(self.by_calls[key])
        return restored
