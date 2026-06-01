# document_ingestion

Pipeline: **PDF / DOC / DOCX → VLM OCR → cleaned Markdown → date-anchored events → SQLite → chronological timeline.**

## Stages

1. **OCR (VLM).** Each page is rendered to PNG and sent to a Vision-Language Model (Claude vision by default, OpenAI gpt-4o fallback) which returns Markdown. DOC/DOCX are converted to PDF via LibreOffice first so signatures and stamps survive.
2. **Clean.** Strip page numbers, fix hyphenation, collapse whitespace.
3. **Extract.** An LLM pass identifies every event with an explicit date and returns `{date, event_detail}` records. A regex fallback runs when no API key is configured.
4. **Persist.** Two SQLite tables — `dates` (one row per calendar day, with the rollup of event ids + source docs) and `events` (one row per `event_id`).
5. **Timeline.** `generate_timeline(store)` walks events in chronological order; `render_markdown` produces a human-readable report.

## Schema

```sql
dates(date PK, event_ids, source_documents)
events(event_id PK, date FK, event_detail, source_documents)
```

Dates are first-class: `dates.date` is the primary key, `events.date` is indexed, and every read path orders by date.

## Credentials

Put keys in `./.api_keys.json` (git-ignored):

```json
{ "anthropic": "sk-ant-..." }
```

Or set `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` in the environment. Override the file location with `DOCING_KEYS_FILE=/path/to/keys.json`.

## Quick start

```bash
pip install -r document_ingestion/requirements.txt
# system: poppler-utils (for pdf2image) and libreoffice (for .doc/.docx)

python -m document_ingestion.cli ingest ./case_docs --workdir ./work
python -m document_ingestion.cli timeline --workdir ./work --out timeline.md
```

## Python API

```python
from document_ingestion import IngestionPipeline, generate_timeline
from document_ingestion.timeline import render_markdown

pipeline = IngestionPipeline(workdir="./work")
pipeline.ingest_directory("./case_docs")

entries = generate_timeline(pipeline.store)
print(render_markdown(entries))
```

## Swapping the VLM

Implement the `VLMClient` protocol (`transcribe(image_png: bytes) -> str`) and pass it in:

```python
IngestionPipeline(workdir="./work", vlm=MyLocalVLM())
```
