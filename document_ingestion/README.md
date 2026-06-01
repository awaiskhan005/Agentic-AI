# document_ingestion

Pipeline: **PDF / DOC / DOCX → local VLM OCR → cleaned Markdown → date-anchored events → SQLite → chronological timeline.**

**100% local.** Every model call goes to a local [Ollama](https://ollama.com) instance — no cloud APIs, no API keys, no data leaving the machine.

## Stages

1. **OCR (local VLM).** Each page is rendered to PNG and sent to a vision model served by Ollama (default: `llama3.2-vision`), which returns Markdown. DOC/DOCX are converted to PDF via LibreOffice first so signatures and stamps survive.
2. **Clean.** Strip page numbers, fix hyphenation, collapse whitespace.
3. **Extract.** A local text model (default: `llama3.1`) identifies every event with an explicit date and returns `{date, event_detail}` records. A regex fallback runs automatically when Ollama is unreachable.
4. **Persist.** Two SQLite tables — `dates` (one row per calendar day, with the rollup of event ids + source docs) and `events` (one row per `event_id`).
5. **Timeline.** `generate_timeline(store)` walks events in chronological order; `render_markdown` produces a human-readable report.

## Schema

```sql
dates(date PK, event_ids, source_documents)
events(event_id PK, date FK, event_detail, source_documents)
```

Dates are first-class: `dates.date` is the primary key, `events.date` is indexed, and every read path orders by date.

## Prerequisites

1. Install and run Ollama:
   ```bash
   ollama serve
   ollama pull llama3.2-vision   # vision / OCR model
   ollama pull llama3.1          # text / event-extraction model
   ```
2. System packages: `poppler-utils` (for pdf2image) and `libreoffice` (for `.doc`/`.docx`).
3. Python deps: `pip install -r document_ingestion/requirements.txt`

## Configuration

No keys needed. Override the endpoint or model names via `./.docing.json`:

```json
{
    "ollama_host": "http://localhost:11434",
    "vision_model": "llama3.2-vision",
    "text_model": "llama3.1"
}
```

Or via environment variables: `OLLAMA_HOST`, `DOCING_VISION_MODEL`, `DOCING_TEXT_MODEL`. Point at a config file elsewhere with `DOCING_CONFIG_FILE=/path/to/config.json`.

## Quick start

```bash
python -m document_ingestion.cli ingest ./case_docs --workdir ./work
python -m document_ingestion.cli timeline --workdir ./work --out timeline.md
```

## Python API

```python
from document_ingestion import IngestionPipeline, generate_timeline
from document_ingestion.timeline import render_markdown

pipeline = IngestionPipeline(workdir="./work")   # uses local Ollama
pipeline.ingest_directory("./case_docs")

entries = generate_timeline(pipeline.store)
print(render_markdown(entries))
```

## Swapping the VLM

The default backend is `OllamaVisionClient`. Any object implementing the `VLMClient` protocol (`transcribe(image_png: bytes) -> str`) can be passed instead — e.g. a different local model server:

```python
IngestionPipeline(workdir="./work", vlm=MyLocalVLM())
```
