"""In-memory simulated workspace: a mailbox and a calendar for one user.

All content is synthetic. An Environment is built fresh from a task JSON for
every episode, so episodes never share state. Anything the agent creates
(sent emails, new events) is flagged so the checks in checks.py can tell
agent actions apart from the seeded data.
"""

from __future__ import annotations

import copy
from dataclasses import asdict, dataclass, field
from datetime import datetime


def parse_dt(value: str) -> datetime:
    """Parse an ISO-8601 datetime. Raises ValueError on bad input."""
    return datetime.fromisoformat(value)


@dataclass
class Email:
    id: str
    sender: str
    to: list[str]
    subject: str
    body: str
    timestamp: str  # ISO-8601
    cc: list[str] = field(default_factory=list)
    folder: str = "inbox"  # "inbox" | "sent"
    read: bool = False
    sent_by_agent: bool = False

    @classmethod
    def from_dict(cls, d: dict) -> "Email":
        return cls(**d)


@dataclass
class Event:
    id: str
    title: str
    start: str  # ISO-8601
    end: str  # ISO-8601
    participants: list[str] = field(default_factory=list)
    location: str = ""
    description: str = ""
    created_by_agent: bool = False

    @classmethod
    def from_dict(cls, d: dict) -> "Event":
        return cls(**d)

    def overlaps(self, start: datetime, end: datetime) -> bool:
        return parse_dt(self.start) < end and start < parse_dt(self.end)


class Mailbox:
    def __init__(self, owner: str, emails: list[Email] | None = None):
        self.owner = owner
        self.emails: list[Email] = list(emails or [])
        self._next_id = len(self.emails) + 1

    def list(
        self,
        folder: str = "inbox",
        unread_only: bool = False,
        query: str | None = None,
        limit: int = 10,
    ) -> list[Email]:
        """Return matching emails, newest first."""
        hits = [e for e in self.emails if e.folder == folder]
        if unread_only:
            hits = [e for e in hits if not e.read]
        if query:
            q = query.lower()
            hits = [
                e for e in hits
                if q in e.subject.lower() or q in e.body.lower() or q in e.sender.lower()
            ]
        hits.sort(key=lambda e: parse_dt(e.timestamp), reverse=True)
        return hits[:limit]

    def send(self, to: list[str], subject: str, body: str, cc: list[str], timestamp: str) -> Email:
        email = Email(
            id=f"sent_{self._next_id}",
            sender=self.owner,
            to=list(to),
            cc=list(cc),
            subject=subject,
            body=body,
            timestamp=timestamp,
            folder="sent",
            read=True,
            sent_by_agent=True,
        )
        self._next_id += 1
        self.emails.append(email)
        return email

    @property
    def sent_by_agent(self) -> list[Email]:
        return [e for e in self.emails if e.sent_by_agent]


class Calendar:
    def __init__(self, events: list[Event] | None = None):
        self.events: list[Event] = list(events or [])
        self._next_id = len(self.events) + 1

    def between(self, start: datetime, end: datetime) -> list[Event]:
        hits = [e for e in self.events if e.overlaps(start, end)]
        hits.sort(key=lambda e: parse_dt(e.start))
        return hits

    def add(
        self,
        title: str,
        start: str,
        end: str,
        participants: list[str],
        location: str,
        description: str,
    ) -> Event:
        event = Event(
            id=f"evt_{self._next_id}",
            title=title,
            start=start,
            end=end,
            participants=list(participants),
            location=location,
            description=description,
            created_by_agent=True,
        )
        self._next_id += 1
        self.events.append(event)
        return event

    @property
    def created_by_agent(self) -> list[Event]:
        return [e for e in self.events if e.created_by_agent]


class Environment:
    """One user's workspace, plus the simulated current time."""

    def __init__(self, user_name: str, user_email: str, now: str,
                 mailbox: Mailbox, calendar: Calendar):
        self.user_name = user_name
        self.user_email = user_email
        self.now = now  # ISO-8601; fixed for the episode so runs are reproducible
        self.mailbox = mailbox
        self.calendar = calendar

    @classmethod
    def from_dict(cls, d: dict) -> "Environment":
        d = copy.deepcopy(d)
        user = d["user"]
        return cls(
            user_name=user["name"],
            user_email=user["email"],
            now=d["now"],
            mailbox=Mailbox(user["email"], [Email.from_dict(e) for e in d.get("emails", [])]),
            calendar=Calendar([Event.from_dict(e) for e in d.get("events", [])]),
        )

    def to_dict(self) -> dict:
        return {
            "user": {"name": self.user_name, "email": self.user_email},
            "now": self.now,
            "emails": [asdict(e) for e in self.mailbox.emails],
            "events": [asdict(e) for e in self.calendar.events],
        }
