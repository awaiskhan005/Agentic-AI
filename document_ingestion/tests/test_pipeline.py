"""Smoke tests that exercise cleaner -> extractor -> store -> timeline.

OCR and the VLM are not exercised here (no PDFs, no API key); the OCR
module is tested separately via a fake VLMClient.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from document_ingestion.cleaner import clean_markdown, clean_file
from document_ingestion.database import EventStore
from document_ingestion.event_extractor import Event, extract_events
from document_ingestion.ocr import OCREngine, VLMClient
from document_ingestion.timeline import generate_timeline, render_markdown


def test_clean_markdown_removes_page_numbers_and_dehyphenates():
    raw = "This is a sen-\ntence.\n\n\n12\n  trailing\n"
    out = clean_markdown(raw)
    assert "sen-\ntence" not in out
    assert "sentence" in out
    assert "\n12\n" not in out
    assert "\n\n\n" not in out


def test_regex_extractor_finds_dates(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    md = tmp_path / "case.md"
    md.write_text(
        "On 2024-01-15 the court denied bail. "
        "The motion was filed on March 3, 2024. "
        "No date here.\n",
        encoding="utf-8",
    )
    events = extract_events(md, use_llm=False)
    dates = sorted(e.date for e in events)
    assert dates == ["2024-01-15", "2024-03-03"]
    assert all(e.source_document == "case.md" for e in events)
    assert all(e.event_id.startswith("eid") for e in events)


def test_event_store_roundtrip_and_rollup(tmp_path: Path):
    store = EventStore(tmp_path / "case.db")
    store.add_events([
        Event("eid001", "2024-01-15", "Bail denied.", "order1.pdf"),
        Event("eid002", "2024-01-15", "Hearing scheduled.", "order2.pdf"),
        Event("eid003", "2024-02-01", "Plea entered.", "order1.pdf"),
    ])

    dates = store.all_dates()
    assert [d["date"] for d in dates] == ["2024-01-15", "2024-02-01"]
    jan = next(d for d in dates if d["date"] == "2024-01-15")
    assert set(jan["event_ids"].split(",")) == {"eid001", "eid002"}
    assert set(jan["source_documents"].split(",")) == {"order1.pdf", "order2.pdf"}

    feb = store.events_on("2024-02-01")
    assert len(feb) == 1 and feb[0]["event_id"] == "eid003"


def test_timeline_is_chronological(tmp_path: Path):
    store = EventStore(tmp_path / "case.db")
    store.add_events([
        Event("eid002", "2024-02-01", "Plea entered.", "order1.pdf"),
        Event("eid001", "2024-01-15", "Bail denied.", "order2.pdf"),
    ])
    entries = generate_timeline(store)
    assert [e.date for e in entries] == ["2024-01-15", "2024-02-01"]
    md = render_markdown(entries)
    assert md.index("2024-01-15") < md.index("2024-02-01")


def test_ocr_engine_uses_provided_vlm(tmp_path: Path):
    class StubVLM:
        def transcribe(self, image_png: bytes) -> str:
            return "stub markdown"

    image = tmp_path / "page.png"
    # 1x1 white PNG
    image.write_bytes(bytes.fromhex(
        "89504e470d0a1a0a0000000d4948445200000001000000010806000000"
        "1f15c4890000000d49444154789c63f8cfc0000000030001011a3a8b8d"
        "0000000049454e44ae426082"
    ))

    engine = OCREngine(output_dir=tmp_path / "out", vlm=StubVLM())
    out = engine.ocr_file(image)
    text = out.read_text(encoding="utf-8")
    assert "stub markdown" in text
    assert "page.png" in text
