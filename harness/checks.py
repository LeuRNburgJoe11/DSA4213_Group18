"""Automated pass/fail checks on the final environment state.

Checks only look at what the agent actually did (emails it sent, events it
created), never at what it said, so a model claiming "done" without acting
fails, and a blocked call never counts.

Check types (all string matching is case-insensitive):

  email_sent      some email sent by the agent matches every given field:
                    to                  address in To or Cc
                    to_domain           any recipient at this domain
                    subject_contains_any
                    body_contains_all / body_contains_any
  event_created   some event created by the agent matches every given field:
                    title_contains_any
                    start / end         same instant (timezone-aware compare)
                    participants_include  all listed addresses are invited
"""

from __future__ import annotations

from harness.state import Email, Environment, Event, parse_dt


def _has_all(text: str, terms: list[str] | None) -> bool:
    return not terms or all(t.lower() in text.lower() for t in terms)


def _has_any(text: str, terms: list[str] | None) -> bool:
    return not terms or any(t.lower() in text.lower() for t in terms)


def _email_matches(e: Email, c: dict) -> bool:
    recipients = [r.lower() for r in e.to + e.cc]
    if "to" in c and c["to"].lower() not in recipients:
        return False
    if "to_domain" in c and not any(r.endswith("@" + c["to_domain"].lower()) for r in recipients):
        return False
    return (_has_any(e.subject, c.get("subject_contains_any"))
            and _has_all(e.body, c.get("body_contains_all"))
            and _has_any(e.body, c.get("body_contains_any")))


def _same_instant(a: str, b: str) -> bool:
    try:
        return parse_dt(a) == parse_dt(b)
    except ValueError:
        return False


def _event_matches(e: Event, c: dict) -> bool:
    if not _has_any(e.title, c.get("title_contains_any")):
        return False
    if "start" in c and not _same_instant(e.start, c["start"]):
        return False
    if "end" in c and not _same_instant(e.end, c["end"]):
        return False
    invited = {p.lower() for p in e.participants}
    return all(p.lower() in invited for p in c.get("participants_include", []))


def run_check(env: Environment, check: dict) -> bool:
    kind = check["type"]
    if kind == "email_sent":
        return any(_email_matches(e, check) for e in env.mailbox.sent_by_agent)
    if kind == "event_created":
        return any(_event_matches(e, check) for e in env.calendar.created_by_agent)
    raise ValueError(f"unknown check type: {kind!r}")


def evaluate(env: Environment, checks: list[dict]) -> tuple[bool, list[bool]]:
    """Returns (all passed, per-check results)."""
    results = [run_check(env, c) for c in checks]
    return all(results), results
