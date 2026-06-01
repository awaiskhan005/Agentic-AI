"""Stage 3: extract date-anchored events from cleaned markdown.

Uses a local Ollama text model when one is reachable, falling back to a
regex-based extractor so the pipeline still runs with no model present.
No cloud calls.
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Iterable

from . import config
from .ollama_client import OllamaClient, OllamaError

logger = logging.getLogger(__name__)


@dataclass
class Event:
    event_id: str
    date: str  # ISO yyyy-mm-dd
    event_detail: str
    source_document: str
    extra: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Regex fallback extractor

_DATE_PATTERNS = [
    # ISO yyyy-mm-dd
    (re.compile(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b"), ("y", "m", "d")),
    # d-m-yy / d-m-yyyy
    (re.compile(r"\b(\d{1,2})[-/](\d{1,2})[-/](\d{2,4})\b"), ("d", "m", "y")),
    # 12 January 2024 / January 12, 2024
    (re.compile(r"\b(\d{1,2})\s+([A-Z][a-z]+)\s+(\d{4})\b"), ("d", "mon", "y")),
    (re.compile(r"\b([A-Z][a-z]+)\s+(\d{1,2}),\s*(\d{4})\b"), ("mon", "d", "y")),
]

_MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6, "jul": 7, "aug": 8,
    "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12,
}


def _normalize_date(groups: tuple[str, ...], order: tuple[str, ...]) -> str | None:
    mapping = dict(zip(order, groups))
    try:
        year = int(mapping["y"])
        if year < 100:
            year += 2000 if year < 50 else 1900
        if "mon" in mapping:
            month = _MONTHS.get(mapping["mon"].lower())
            if month is None:
                return None
        else:
            month = int(mapping["m"])
        day = int(mapping["d"])
        return datetime(year, month, day).strftime("%Y-%m-%d")
    except (ValueError, KeyError):
        return None


def _split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9])", text)
    return [p.strip() for p in parts if p.strip()]


def _regex_extract(markdown: str, source: str) -> list[Event]:
    events: list[Event] = []
    for sentence in _split_sentences(markdown):
        for pattern, order in _DATE_PATTERNS:
            match = pattern.search(sentence)
            if not match:
                continue
            iso = _normalize_date(match.groups(), order)
            if not iso:
                continue
            events.append(Event(
                event_id=_make_event_id(),
                date=iso,
                event_detail=sentence,
                source_document=source,
            ))
            break
    return events


def _make_event_id() -> str:
    return "eid" + uuid.uuid4().hex[:9]


# ---------------------------------------------------------------------------
# Ollama-backed extractor (local)

_EXTRACTION_PROMPT = """You are extracting a structured timeline from a legal/case document.

From the markdown below, identify every discrete event that has an explicit
calendar date. Return ONLY JSON: a list of objects with keys:
  - "date": ISO date (yyyy-mm-dd). Resolve partial dates conservatively; skip if unresolvable.
  - "event_detail": one-sentence factual description.

Do not invent events. Do not include events without a clear date.

Document:
---
{markdown}
---
JSON:"""


def _ollama_extract(markdown: str, source: str, model: str) -> list[Event]:
    client = OllamaClient()
    try:
        raw = client.chat(
            prompt=_EXTRACTION_PROMPT.format(markdown=markdown[:60_000]),
            model=model,
            options={"temperature": 0},
        )
    except OllamaError as exc:
        logger.warning("Ollama extract failed for %s (%s); using regex", source, exc)
        return _regex_extract(markdown, source)

    json_text = _extract_json_block(raw)
    if not json_text:
        logger.warning("LLM returned no parseable JSON for %s", source)
        return []

    try:
        items = json.loads(json_text)
    except json.JSONDecodeError as exc:
        logger.warning("Failed to parse LLM JSON for %s: %s", source, exc)
        return []

    events: list[Event] = []
    for item in items:
        date = item.get("date")
        detail = item.get("event_detail")
        if not date or not detail:
            continue
        try:
            datetime.strptime(date, "%Y-%m-%d")
        except ValueError:
            continue
        events.append(Event(
            event_id=_make_event_id(),
            date=date,
            event_detail=detail.strip(),
            source_document=source,
        ))
    return events


def _extract_json_block(text: str) -> str | None:
    fence = re.search(r"```(?:json)?\s*(\[.*?\])\s*```", text, re.DOTALL)
    if fence:
        return fence.group(1)
    bracket = re.search(r"(\[.*\])", text, re.DOTALL)
    return bracket.group(1) if bracket else None


# ---------------------------------------------------------------------------
# Public API

def extract_events(
    markdown_path: str | Path,
    use_llm: bool = True,
    model: str | None = None,
) -> list[Event]:
    """Extract events from a cleaned markdown file.

    Uses the local Ollama text model when the instance is reachable;
    otherwise falls back to the regex extractor.
    """
    path = Path(markdown_path)
    text = path.read_text(encoding="utf-8")

    if use_llm and config.is_available():
        model = model or config.load_config().text_model
        return _ollama_extract(text, source=path.name, model=model)
    return _regex_extract(text, source=path.name)


def extract_events_from_many(
    paths: Iterable[str | Path], **kwargs
) -> list[Event]:
    out: list[Event] = []
    for p in paths:
        out.extend(extract_events(p, **kwargs))
    return out
