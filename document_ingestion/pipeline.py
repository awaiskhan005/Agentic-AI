"""End-to-end orchestration: PDF/DOC -> Markdown -> Events -> SQLite."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

from .cleaner import clean_file
from .database import EventStore
from .event_extractor import Event, extract_events
from .ocr import OCREngine, VLMClient

logger = logging.getLogger(__name__)


@dataclass
class IngestionResult:
    raw_markdown: list[Path] = field(default_factory=list)
    clean_markdown: list[Path] = field(default_factory=list)
    events: list[Event] = field(default_factory=list)


class IngestionPipeline:
    """Run the four pipeline stages on a folder of source documents.

    Layout under `workdir`:
        raw_md/      -- VLM transcription per source file
        clean_md/    -- post-OCR cleanup
        case.db      -- SQLite store
    """

    def __init__(
        self,
        workdir: str | Path,
        db_path: str | Path | None = None,
        vlm: VLMClient | None = None,
        llm_model: str = "claude-opus-4-7",
        use_llm_for_events: bool = True,
    ):
        self.workdir = Path(workdir)
        self.raw_dir = self.workdir / "raw_md"
        self.clean_dir = self.workdir / "clean_md"
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self.clean_dir.mkdir(parents=True, exist_ok=True)

        self.ocr = OCREngine(output_dir=self.raw_dir, vlm=vlm)
        self.store = EventStore(db_path or self.workdir / "case.db")
        self.llm_model = llm_model
        self.use_llm_for_events = use_llm_for_events

    def ingest_directory(self, src_dir: str | Path) -> IngestionResult:
        result = IngestionResult()
        result.raw_markdown = self.ocr.ocr_directory(src_dir)
        for raw in result.raw_markdown:
            cleaned = clean_file(raw, self.clean_dir)
            result.clean_markdown.append(cleaned)
            events = extract_events(
                cleaned,
                use_llm=self.use_llm_for_events,
                model=self.llm_model,
            )
            result.events.extend(events)
            self.store.add_events(events)
        logger.info(
            "Ingested %d documents, extracted %d events",
            len(result.raw_markdown), len(result.events),
        )
        return result

    def ingest_file(self, source: str | Path) -> IngestionResult:
        result = IngestionResult()
        raw = self.ocr.ocr_file(source)
        cleaned = clean_file(raw, self.clean_dir)
        events = extract_events(
            cleaned,
            use_llm=self.use_llm_for_events,
            model=self.llm_model,
        )
        self.store.add_events(events)
        result.raw_markdown = [raw]
        result.clean_markdown = [cleaned]
        result.events = events
        return result
