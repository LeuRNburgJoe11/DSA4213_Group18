"""
RQ2: base parameter-open tasks, registered as AgentDojo user tasks.

"Parameter-open" means the user prompt leaves one parameter (e.g. which
address to send to) for the agent to resolve from the environment, which is
where an attacker can plant a competing value. Each task records the correct
value and the attacker's value so `outcome.py` can label the episode.
"""

from __future__ import annotations

# TODO: register on the workspace suite, e.g.
#   from agentdojo.default_suites.v1.workspace.task_suite import task_suite
#   @task_suite.register_user_task
#   class IdentityTask0(BaseUserTask[WorkspaceEnvironment]): ...

TASK_PARAMS: dict[str, dict] = {}  # task_id -> {"correct": ..., "attacker": ...}
