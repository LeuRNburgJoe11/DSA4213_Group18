"""Episode and tool-call logging.

Every episode writes one JSONL trajectory file (one record per event) under
runs/<run_id>/episodes/, and appends a one-line summary to
runs/<run_id>/results.jsonl, which is the file the metrics are computed from.

Record types in a trajectory:
  episode_start  config, task id, variant, user prompt
  llm_call       turn, stop_reason, assistant text, token usage, latency
  tool_call      turn, name, args, side_effecting, executed, blocked, output
  defense        any decision a defense wants on record (plans, verdicts)
  episode_end    termination reason, final response, counts
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _jsonable(obj: Any) -> Any:
    """Best-effort conversion of SDK objects to plain JSON."""
    if hasattr(obj, "model_dump"):
        return obj.model_dump(mode="json", exclude_none=True)
    if isinstance(obj, dict):
        return {k: _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_jsonable(v) for v in obj]
    if isinstance(obj, (str, int, float, bool)) or obj is None:
        return obj
    return str(obj)


@dataclass
class ToolCallRecord:
    turn: int
    tool_use_id: str
    name: str
    args: dict
    side_effecting: bool
    executed: bool  # False if blocked by a defense or skipped for budget
    blocked: bool
    block_reason: str | None
    output: str  # what the model saw (after any defense formatting)
    is_error: bool


@dataclass
class EpisodeLogger:
    run_dir: Path
    episode_id: str
    records: list[dict] = field(default_factory=list)
    tool_calls: list[ToolCallRecord] = field(default_factory=list)
    usage: dict[str, int] = field(default_factory=dict)
    _t0: float = field(default_factory=time.perf_counter)

    def __post_init__(self) -> None:
        self.run_dir = Path(self.run_dir)
        (self.run_dir / "episodes").mkdir(parents=True, exist_ok=True)
        self.path = self.run_dir / "episodes" / f"{self.episode_id}.jsonl"
        self._fh = self.path.open("w", encoding="utf-8")

    # -- generic -----------------------------------------------------------
    def log(self, kind: str, **data: Any) -> None:
        rec = {
            "type": kind,
            "t": round(time.perf_counter() - self._t0, 3),
            "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            **_jsonable(data),
        }
        self.records.append(rec)
        self._fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        self._fh.flush()

    # -- typed helpers -----------------------------------------------------
    def episode_start(self, **data: Any) -> None:
        self.log("episode_start", episode_id=self.episode_id, **data)

    def llm_call(self, turn: int, stop_reason: str | None, text: str,
                 tool_uses: list[dict], usage: dict[str, int], latency_s: float,
                 raw_content: Any = None) -> None:
        for k, v in usage.items():
            if isinstance(v, int):
                self.usage[k] = self.usage.get(k, 0) + v
        self.log("llm_call", turn=turn, stop_reason=stop_reason, text=text,
                 tool_uses=tool_uses, usage=usage, latency_s=round(latency_s, 3),
                 raw_content=raw_content)

    def tool_call(self, rec: ToolCallRecord) -> None:
        self.tool_calls.append(rec)
        self.log("tool_call", **rec.__dict__)

    def defense(self, name: str, **data: Any) -> None:
        self.log("defense", defense=name, **data)

    def episode_end(self, **data: Any) -> None:
        self.log("episode_end", **data)
        self._fh.close()

    # -- derived counts ----------------------------------------------------
    @property
    def side_effect_calls(self) -> list[ToolCallRecord]:
        return [c for c in self.tool_calls if c.side_effecting and c.executed]

    @property
    def blocked_calls(self) -> list[ToolCallRecord]:
        return [c for c in self.tool_calls if c.blocked]


def append_result(run_dir: Path, summary: dict) -> None:
    """Append one episode summary line to runs/<run_id>/results.jsonl."""
    run_dir = Path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    with (run_dir / "results.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(_jsonable(summary), ensure_ascii=False) + "\n")
