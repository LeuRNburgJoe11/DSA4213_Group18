"""
RQ3: sender gate, a pipeline element that blocks side-effecting tool calls
whose arguments came from untrusted content.

  mode="origin"         - trust is decided by where the value came from
                          (user prompt vs tool output)
  mode="origin+sender"  - additionally trusts tool output from known senders
"""

from __future__ import annotations

MODES = ("origin", "origin+sender")


class SenderGate:
    """AgentDojo BasePipelineElement placed before ToolsExecutor."""

    def __init__(self, mode: str = "origin", trusted_senders: set[str] | None = None):
        if mode not in MODES:
            raise ValueError(f"mode must be one of {MODES}")
        self.mode = mode
        self.trusted_senders = trusted_senders or set()

    def query(self, query, runtime, env, messages, extra_args):
        raise NotImplementedError
