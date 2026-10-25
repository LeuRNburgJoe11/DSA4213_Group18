"""
RQ3: evidence-based recipient verification gate.

Wraps AgentDojo's ToolsExecutor. Before a ``send_email`` call runs, every recipient
(To, Cc and Bcc) is checked against evidence in the environment. Calls the gate
holds are not executed; the agent gets an error result for that call id instead,
and every other tool call in the same step still runs. One uncertain recipient
therefore never stalls unrelated sends.

Verdict for a send_email call, from its recipients:

  every recipient supported      -> ALLOW  (the call runs)
  no recipient supported         -> ASK    (held; ask the user to confirm the address)
  some supported, some not       -> BLOCK  (held; an extra unverified recipient)

A recipient is "supported" when (each mode includes the one above it):

  mode="origin"           user_supplied: the address appears in the user's request
  mode="origin+readers"   file_reader: it is a reader of a file attached to this email
                          (CaMeL-style: the data may go to people who can already read it)
  mode="origin+identity"  ... or any of
      authorised_update   an inbox email from an established sender names it
                          (an explicit change notice from a trusted source)
      contact             it is in the user's own address book
      sent_history        an email the user sent before the episode started went to it

"Anchored": when an attached file has readers other than the user's own account, that
reader list is the identity anchor. Then sent history alone does NOT support a recipient
(a known correspondent is not thereby the file's intended reader), and only readers can
vouch for an update. With no external reader (e.g. a document shared only with the user),
sent history is the anchor instead.

Not treated as evidence: sign-offs and display names, address similarity, how accurate
an email's meeting details are, and a change that only the new address asserts.

Assumptions to state when reporting results:
  - Mailbox history, file readers and the contact list are outside the attacker's control
    (the attacker can send mail, not edit existing history). If history can be forged,
    "sent_history" proves nothing. AgentDojo builds a default contact list from the
    addresses in the initial emails, so "contact" is only safe where the fixture sets
    contacts explicitly (true for the RQ2 task25 fixture, which has no attacker contact).
  - Where history and contextual accuracy disagree, history wins. That is a policy
    choice, so results on those conditions follow from the policy by construction.
  - The gate reads only the environment and the user's request. It never receives the
    evaluator's genuine/attacker labels, and the agent's own sends never count as
    history (history is snapshotted before the first call).
"""

from __future__ import annotations

import re
from ast import literal_eval
from collections.abc import Sequence
from dataclasses import dataclass, field

from agentdojo.agent_pipeline.base_pipeline_element import BasePipelineElement
from agentdojo.agent_pipeline.tool_execution import ToolsExecutor
from agentdojo.default_suites.v1.tools.types import EmailStatus
from agentdojo.functions_runtime import EmptyEnv, Env, FunctionsRuntime
from agentdojo.types import ChatMessage, ChatToolResultMessage, text_content_block_from_string

MODES = ("origin", "origin+readers", "origin+identity")

# Verdicts for one recipient and for a whole tool call.
ALLOW, BLOCK, ASK = "allow", "block", "ask"

SEND_TOOL = "send_email"
_ADDRESS = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")


def _norm(address: str) -> str:
    return address.strip().lower()


def _addresses(text: str) -> set[str]:
    return {_norm(a) for a in _ADDRESS.findall(text or "")}


def _as_list(value) -> list[str]:
    """Recipient arguments arrive as a list, None, or a stringified list."""
    if value is None:
        return []
    if isinstance(value, str):
        try:
            parsed = literal_eval(value)
        except (ValueError, SyntaxError):
            parsed = None
        value = parsed if isinstance(parsed, list) else [value]
    return [_norm(str(v)) for v in value]


@dataclass(frozen=True)
class RecipientVerdict:
    address: str
    verdict: str  # ALLOW or ASK (an unsupported recipient is always ASK; BLOCK is per call)
    reason: str


@dataclass(frozen=True)
class Decision:
    verdict: str
    recipients: tuple[RecipientVerdict, ...]

    def as_dict(self) -> dict:
        return {"verdict": self.verdict,
                "recipients": [{"address": r.address, "verdict": r.verdict, "reason": r.reason}
                               for r in self.recipients]}

    @property
    def unsupported(self) -> list[str]:
        return [r.address for r in self.recipients if r.verdict != ALLOW]

    @property
    def message(self) -> str:
        who = ", ".join(self.unsupported)
        if self.verdict == BLOCK:
            return (f"Not sent: {who} could not be verified, although other recipients of this email could. "
                    "Do not add unverified recipients. Ask the user to confirm the address before sending.")
        return (f"Not sent: no evidence supports the address(es) {who}. "
                "Ask the user to confirm which address to use before sending anything.")


class RecipientGate(BasePipelineElement):
    """Pipeline element that stands in for ToolsExecutor and vets send_email calls."""

    name = "recipient_gate"

    def __init__(self, mode: str = "origin", executor: ToolsExecutor | None = None):
        if mode not in MODES:
            raise ValueError(f"mode must be one of {MODES}")
        self.mode = mode
        self.executor = executor or ToolsExecutor()
        self.decisions: list[Decision] = []
        self._history: set[str] | None = None

    # -- evidence -------------------------------------------------------------------

    def snapshot(self, env) -> None:
        """Record the addresses the user had already sent to. Call before the agent acts."""
        sent = [e for e in env.inbox.emails.values() if e.status == EmailStatus.sent]
        self._history = {_norm(a) for e in sent for a in (*e.recipients, *e.cc, *e.bcc)}

    def _file_readers(self, args, env) -> set[str]:
        readers: set[str] = set()
        files = getattr(getattr(env, "cloud_drive", None), "files", {})
        for attachment in args.get("attachments") or []:
            if isinstance(attachment, dict) and "file_id" in attachment:
                file = files.get(str(attachment["file_id"]))
                if file is not None:
                    readers |= {_norm(a) for a in file.shared_with}
        return readers

    def _authorised_updates(self, env, established: set[str]) -> dict[str, str]:
        """New address -> the established sender whose email names it."""
        updates: dict[str, str] = {}
        for email in env.inbox.emails.values():
            if email.status != EmailStatus.received or _norm(email.sender) not in established:
                continue
            for address in _addresses(f"{email.subject} {email.body}"):
                updates.setdefault(address, _norm(email.sender))
        return updates

    # -- decision -------------------------------------------------------------------

    def evaluate(self, args, env, user_query: str) -> Decision:
        if self._history is None:
            self.snapshot(env)
        recipients = list(dict.fromkeys(
            _as_list(args.get("recipients")) + _as_list(args.get("cc")) + _as_list(args.get("bcc"))))
        supplied = _addresses(user_query)
        identity = self.mode == "origin+identity"
        readers = self._file_readers(args, env) if self.mode != "origin" else set()
        own = _norm(getattr(env.inbox, "account_email", ""))
        anchored = bool(readers - {own})  # an external reader of an attachment anchors identity
        history = self._history if identity else set()
        contacts = {_norm(c.email) for c in env.inbox.contact_list} if identity else set()
        # Who may vouch for a change: the file's external readers if anchored, else past recipients.
        trusted_senders = (readers - {own}) if anchored else history
        updates = self._authorised_updates(env, trusted_senders) if identity else {}

        verdicts = []
        for address in recipients:
            if address in supplied:
                reason = "user_supplied"
            elif address in readers:
                reason = "file_reader"
            elif address in updates:
                reason = f"authorised_update_from:{updates[address]}"
            elif address in contacts:
                reason = "contact"
            elif address in history and not anchored:
                reason = "sent_history"
            else:
                verdicts.append(RecipientVerdict(address, ASK, "unverified"))
                continue
            verdicts.append(RecipientVerdict(address, ALLOW, reason))

        supported = [v for v in verdicts if v.verdict == ALLOW]
        if len(supported) == len(verdicts):
            overall = ALLOW
        elif not supported:
            overall = ASK
        else:
            overall = BLOCK
        return Decision(overall, tuple(verdicts))

    # -- pipeline -------------------------------------------------------------------

    def query(
        self,
        query: str,
        runtime: FunctionsRuntime,
        env: Env = EmptyEnv(),
        messages: Sequence[ChatMessage] = [],
        extra_args: dict = {},
    ):
        last = messages[-1] if messages else None
        if last is None or last["role"] != "assistant" or not last.get("tool_calls"):
            return self.executor.query(query, runtime, env, messages, extra_args)

        allowed, held = [], {}
        for call in last["tool_calls"]:
            if call.function == SEND_TOOL:
                decision = self.evaluate(call.args, env, query)
                self.decisions.append(decision)
                if decision.verdict != ALLOW:
                    held[call.id] = (call, decision)
                    continue
            allowed.append(call)

        inner_last = {**last, "tool_calls": allowed}
        query, runtime, env, inner, extra_args = self.executor.query(
            query, runtime, env, [*messages[:-1], inner_last], extra_args)
        executed = {m["tool_call"].id: m for m in inner[len(messages):]}

        results = []
        for call in last["tool_calls"]:
            if call.id in held:
                _, decision = held[call.id]
                results.append(ChatToolResultMessage(
                    role="tool", content=[text_content_block_from_string("")],
                    tool_call_id=call.id, tool_call=call, error=decision.message))
            else:
                results.append(executed[call.id])
        return query, runtime, env, [*messages, *results], extra_args
