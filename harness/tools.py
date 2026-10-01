"""The four agent tools: read_emails, send_email, read_calendar, create_event.

Each tool is a plain function `(env, **args) -> str`. The returned string is
exactly what the model sees as the tool result (before any defense wraps it).
Bad arguments raise ToolError; the agent loop turns that into an error result.

TOOL_SCHEMAS holds the JSON-schema definitions passed to the LLM API.
SIDE_EFFECTING names the tools whose calls count toward attack success.
"""

from __future__ import annotations

from datetime import datetime, time, timedelta
from typing import Callable

from harness.state import Email, Environment, Event, parse_dt


class ToolError(Exception):
    """Raised for invalid tool arguments; reported back to the model."""


SIDE_EFFECTING = frozenset({"send_email", "create_event"})


# ---------------------------------------------------------------------------
# Rendering helpers
# ---------------------------------------------------------------------------

def _render_email(e: Email) -> str:
    lines = [
        f"ID: {e.id}",
        f"From: {e.sender}",
        f"To: {', '.join(e.to)}",
    ]
    if e.cc:
        lines.append(f"Cc: {', '.join(e.cc)}")
    lines += [f"Date: {e.timestamp}", f"Subject: {e.subject}", "", e.body]
    return "\n".join(lines)


def _render_event(e: Event) -> str:
    lines = [
        f"ID: {e.id}",
        f"Title: {e.title}",
        f"Start: {e.start}",
        f"End: {e.end}",
    ]
    if e.participants:
        lines.append(f"Participants: {', '.join(e.participants)}")
    if e.location:
        lines.append(f"Location: {e.location}")
    if e.description:
        lines.append(f"Description: {e.description}")
    return "\n".join(lines)


def _require_str(args: dict, key: str) -> str:
    value = args.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ToolError(f"'{key}' must be a non-empty string")
    return value


def _str_list(args: dict, key: str, required: bool = False) -> list[str]:
    value = args.get(key)
    if value is None:
        if required:
            raise ToolError(f"'{key}' is required")
        return []
    if isinstance(value, str):  # tolerate a single address passed as a string
        value = [value]
    if not isinstance(value, list) or not all(isinstance(v, str) and v.strip() for v in value):
        raise ToolError(f"'{key}' must be a list of non-empty strings")
    if required and not value:
        raise ToolError(f"'{key}' must contain at least one entry")
    return value


def _validate_addresses(addresses: list[str]) -> None:
    for a in addresses:
        if "@" not in a or " " in a.strip():
            raise ToolError(f"invalid email address: {a!r}")


def _parse(value: str, key: str) -> datetime:
    try:
        return parse_dt(value)
    except (TypeError, ValueError):
        raise ToolError(f"'{key}' must be an ISO-8601 datetime, got {value!r}") from None


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

def read_emails(env: Environment, folder: str = "inbox", unread_only: bool = False,
                query: str | None = None, limit: int = 10) -> str:
    if folder not in ("inbox", "sent"):
        raise ToolError("'folder' must be 'inbox' or 'sent'")
    if not isinstance(limit, int) or not 1 <= limit <= 50:
        raise ToolError("'limit' must be an integer between 1 and 50")
    emails = env.mailbox.list(folder=folder, unread_only=bool(unread_only), query=query, limit=limit)
    if not emails:
        return "No emails found."
    for e in emails:
        e.read = True
    return f"Found {len(emails)} email(s):\n\n" + "\n\n---\n\n".join(_render_email(e) for e in emails)


def send_email(env: Environment, to: list[str], subject: str, body: str,
               cc: list[str] | None = None) -> str:
    to_list = _str_list({"to": to}, "to", required=True)
    cc_list = _str_list({"cc": cc}, "cc")
    _validate_addresses(to_list + cc_list)
    subject = _require_str({"subject": subject}, "subject")
    if not isinstance(body, str):
        raise ToolError("'body' must be a string")
    sent = env.mailbox.send(to_list, subject, body, cc_list, timestamp=env.now)
    return f"Email sent (ID: {sent.id}) to {', '.join(sent.to)}."


def read_calendar(env: Environment, date: str | None = None,
                  start_date: str | None = None, end_date: str | None = None) -> str:
    """Events on `date`, or in [start_date, end_date]; defaults to today."""
    tz = parse_dt(env.now).tzinfo
    if date and (start_date or end_date):
        raise ToolError("pass either 'date' or 'start_date'/'end_date', not both")
    try:
        if start_date or end_date:
            if not (start_date and end_date):
                raise ToolError("both 'start_date' and 'end_date' are required for a range")
            first = datetime.fromisoformat(start_date).date()
            last = datetime.fromisoformat(end_date).date()
        else:
            day = datetime.fromisoformat(date).date() if date else parse_dt(env.now).date()
            first = last = day
    except ValueError:
        raise ToolError("dates must be ISO-8601, e.g. 2026-10-05") from None
    if last < first:
        raise ToolError("'end_date' is before 'start_date'")
    if (last - first).days > 31:
        raise ToolError("date range may span at most 31 days")

    window_start = datetime.combine(first, time.min, tzinfo=tz)
    window_end = datetime.combine(last + timedelta(days=1), time.min, tzinfo=tz)
    events = env.calendar.between(window_start, window_end)
    span = first.isoformat() if first == last else f"{first.isoformat()} to {last.isoformat()}"
    if not events:
        return f"No events on {span}."
    return f"{len(events)} event(s) on {span}:\n\n" + "\n\n---\n\n".join(_render_event(e) for e in events)


def create_event(env: Environment, title: str, start: str, end: str,
                 participants: list[str] | None = None, location: str = "",
                 description: str = "") -> str:
    title = _require_str({"title": title}, "title")
    start_dt = _parse(start, "start")
    end_dt = _parse(end, "end")
    if (start_dt.tzinfo is None) != (end_dt.tzinfo is None):
        raise ToolError("'start' and 'end' must both include a timezone offset or both omit it")
    if start_dt.tzinfo is None:  # assume the user's timezone
        tz = parse_dt(env.now).tzinfo
        start_dt, end_dt = start_dt.replace(tzinfo=tz), end_dt.replace(tzinfo=tz)
    if end_dt <= start_dt:
        raise ToolError("'end' must be after 'start'")
    people = _str_list({"participants": participants}, "participants")
    _validate_addresses(people)
    event = env.calendar.add(title, start_dt.isoformat(), end_dt.isoformat(),
                             people, location or "", description or "")
    clashes = [e for e in env.calendar.between(start_dt, end_dt) if e.id != event.id]
    note = f" Note: overlaps with {', '.join(c.title for c in clashes)}." if clashes else ""
    return f"Event created (ID: {event.id}): {event.title}, {event.start} to {event.end}.{note}"


TOOLS: dict[str, Callable[..., str]] = {
    "read_emails": read_emails,
    "send_email": send_email,
    "read_calendar": read_calendar,
    "create_event": create_event,
}


def execute_tool(env: Environment, name: str, args: dict) -> tuple[str, bool]:
    """Run a tool. Returns (output, is_error)."""
    fn = TOOLS.get(name)
    if fn is None:
        return f"Error: unknown tool {name!r}", True
    if not isinstance(args, dict):
        return "Error: tool arguments must be a JSON object", True
    try:
        return fn(env, **args), False
    except ToolError as exc:
        return f"Error: {exc}", True
    except TypeError as exc:  # unexpected or missing keyword arguments
        return f"Error: invalid arguments for {name}: {exc}", True


# ---------------------------------------------------------------------------
# Schemas sent to the LLM (Anthropic tool format; other backends convert)
# ---------------------------------------------------------------------------

TOOL_SCHEMAS: list[dict] = [
    {
        "name": "read_emails",
        "description": (
            "List emails in the user's mailbox, newest first. Returns sender, recipients, "
            "date, subject and full body of each email, and marks them as read."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "folder": {"type": "string", "enum": ["inbox", "sent"],
                           "description": "Mailbox folder. Default: inbox."},
                "unread_only": {"type": "boolean", "description": "Only unread emails. Default: false."},
                "query": {"type": "string",
                          "description": "Case-insensitive text to match in subject, body or sender."},
                "limit": {"type": "integer", "minimum": 1, "maximum": 50,
                          "description": "Maximum emails to return. Default: 10."},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "send_email",
        "description": "Send an email from the user's account.",
        "input_schema": {
            "type": "object",
            "properties": {
                "to": {"type": "array", "items": {"type": "string"}, "description": "Recipient addresses."},
                "subject": {"type": "string"},
                "body": {"type": "string"},
                "cc": {"type": "array", "items": {"type": "string"}, "description": "Optional CC addresses."},
            },
            "required": ["to", "subject", "body"],
            "additionalProperties": False,
        },
    },
    {
        "name": "read_calendar",
        "description": (
            "List calendar events on one day ('date') or across a range ('start_date' and "
            "'end_date', at most 31 days). With no arguments, returns today's events."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "date": {"type": "string", "description": "Day in YYYY-MM-DD format."},
                "start_date": {"type": "string", "description": "Range start, YYYY-MM-DD."},
                "end_date": {"type": "string", "description": "Range end (inclusive), YYYY-MM-DD."},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "create_event",
        "description": "Create an event on the user's calendar.",
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "start": {"type": "string",
                          "description": "ISO-8601 datetime, e.g. 2026-10-06T14:00:00+08:00."},
                "end": {"type": "string", "description": "ISO-8601 datetime, after start."},
                "participants": {"type": "array", "items": {"type": "string"},
                                 "description": "Attendee email addresses."},
                "location": {"type": "string"},
                "description": {"type": "string"},
            },
            "required": ["title", "start", "end"],
            "additionalProperties": False,
        },
    },
]
