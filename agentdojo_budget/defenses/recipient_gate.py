"""
RQ3: evidence-based recipient verification gate, a pipeline element that checks
every recipient (To, Cc and Bcc) of a side-effecting tool call before it runs.

  mode="origin"            - trust is decided by where the address came from
                             (user prompt vs tool output)
  mode="origin+identity"   - additionally requires that available evidence
                             supports each destination address

The gate decides per recipient, so one uncertain recipient does not stall
unrelated sends in the same episode. It sees only the environment state, never
the evaluator's genuine/attacker labels.
"""

from __future__ import annotations

MODES = ("origin", "origin+identity")

# Verdicts for one recipient; a tool call's verdict is the strictest of its recipients.
ALLOW, BLOCK, ASK = "allow", "block", "ask"


class RecipientGate:
    """AgentDojo BasePipelineElement placed before ToolsExecutor."""

    def __init__(self, mode: str = "origin"):
        if mode not in MODES:
            raise ValueError(f"mode must be one of {MODES}")
        self.mode = mode

    def query(self, query, runtime, env, messages, extra_args):
        raise NotImplementedError
