"""
RQ2: the 5 identity conditions, expressed as edits to an AgentDojo environment.

Each condition takes a base task's environment and changes only what the agent
can see about who is asking (e.g. sender address, display name, thread
history), so the user prompt and the tools stay identical across conditions.
"""

from __future__ import annotations

CONDITIONS: list[str] = []  # TODO: the 5 condition names, in slide order


def apply_condition(environment, condition: str, task_params: dict):
    """Return a copy of `environment` edited for `condition`.

    Must not mutate the input: AgentDojo reuses the loaded environment.
    """
    raise NotImplementedError
