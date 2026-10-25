"""
ask_user tool: lets the agent ask the user a clarifying question.

Calling it ends the episode, so the question itself is the outcome
(labelled "asked" by `outcome.py`); no simulated user answers it.
"""

from __future__ import annotations


def ask_user(question: str) -> str:
    """Ask the user a clarifying question. Use this when you are unsure which value the user wants.

    :param question: the question to show the user.
    """
    raise NotImplementedError  # TODO: register as an AgentDojo tool and stop the tool loop
