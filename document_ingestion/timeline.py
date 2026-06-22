"""Stage 5: generate a chronological timeline from the EventStore."""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Iterable

from .database import EventStore


@dataclass
class TimelineEntry:
    date: str
    event_id: str
    event_detail: str
    source_documents: str

    def as_dict(self) -> dict:
        return asdict(self)


def generate_timeline(store: EventStore) -> list[TimelineEntry]:
    """Return every event in chronological order, oldest first."""
    return [
        TimelineEntry(
            date=row["date"],
            event_id=row["event_id"],
            event_detail=row["event_detail"],
            source_documents=row["source_documents"],
        )
        for row in store.iter_events_chronologically()
    ]


def render_markdown(entries: Iterable[TimelineEntry]) -> str:
    """Render a timeline as a human-readable markdown report."""
    lines = ["# Case Timeline\n"]
    current_date = None
    for entry in entries:
        if entry.date != current_date:
            lines.append(f"\n## {entry.date}\n")
            current_date = entry.date
        lines.append(
            f"- **[{entry.event_id}]** {entry.event_detail}  \n"
            f"  _source: {entry.source_documents}_"
        )
    return "\n".join(lines) + "\n"
