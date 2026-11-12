"""System Trace Observer — a passive, always-on log.

The observer never modifies anything; it only records what
happened, when, where, how, and why, and prints the full log when
asked. Every event carries the five trace fields from the spec.
"""
from __future__ import annotations

import datetime
from dataclasses import dataclass, field


@dataclass
class TraceEvent:
    what: str
    where: str = ""
    how: str = ""
    why: str = ""
    when: str = ""

    def __post_init__(self):
        if not self.when:
            self.when = datetime.datetime.now(
                datetime.timezone.utc).isoformat(timespec="seconds")


class Trace:
    """An ordered log of events. Passive by design."""

    def __init__(self):
        self.events = []

    def log(self, what, where="", how="", why=""):
        self.events.append(TraceEvent(what=what, where=where,
                                      how=how, why=why))

    def __len__(self):
        return len(self.events)

    def render(self):
        """The full log as a single code block, per the spec."""
        lines = ["```", "SKRIBE TRACE"]
        for event in self.events:
            lines.append(f"- [{event.when}] {event.what}")
            if event.where:
                lines.append(f"  where: {event.where}")
            if event.how:
                lines.append(f"  how: {event.how}")
            if event.why:
                lines.append(f"  why: {event.why}")
        lines.append("```")
        return "\n".join(lines)

    def to_dict(self):
        return [{
            "what": e.what, "when": e.when, "where": e.where,
            "how": e.how, "why": e.why,
        } for e in self.events]
