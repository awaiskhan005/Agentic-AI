"""Command-line entrypoint for the ingestion pipeline.

Usage:
    python -m document_ingestion.cli ingest <src_dir> --workdir ./work
    python -m document_ingestion.cli timeline --workdir ./work [--out timeline.md]
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from .database import EventStore
from .pipeline import IngestionPipeline
from .timeline import generate_timeline, render_markdown


def _ingest(args: argparse.Namespace) -> int:
    pipeline = IngestionPipeline(
        workdir=args.workdir,
        use_llm_for_events=not args.no_llm,
    )
    result = pipeline.ingest_directory(args.src_dir)
    print(f"Ingested {len(result.raw_markdown)} docs, {len(result.events)} events")
    return 0


def _timeline(args: argparse.Namespace) -> int:
    db_path = Path(args.workdir) / "case.db"
    store = EventStore(db_path)
    entries = generate_timeline(store)
    output = render_markdown(entries)
    if args.out:
        Path(args.out).write_text(output, encoding="utf-8")
        print(f"Wrote {len(entries)} events to {args.out}")
    else:
        sys.stdout.write(output)
    return 0


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    parser = argparse.ArgumentParser(prog="document_ingestion")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_ingest = sub.add_parser("ingest", help="OCR + extract events from a folder")
    p_ingest.add_argument("src_dir", help="folder with .pdf/.doc/.docx files")
    p_ingest.add_argument("--workdir", default="./work")
    p_ingest.add_argument("--no-llm", action="store_true",
                          help="use regex-only event extraction")
    p_ingest.set_defaults(func=_ingest)

    p_tl = sub.add_parser("timeline", help="render the chronological timeline")
    p_tl.add_argument("--workdir", default="./work")
    p_tl.add_argument("--out", help="write markdown to this file (default: stdout)")
    p_tl.set_defaults(func=_timeline)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
