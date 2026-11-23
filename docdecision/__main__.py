from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .decision import decide_document
from .document import ReadError
from .extract import load_field_specs
from .rules import RuleEngine, load_engine


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="docdecision",
        description="Read incoming documents and suggest a decision.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    def common(p):
        p.add_argument("documents", nargs="+", type=Path, help="documents to read")
        p.add_argument("--fields", default=str(_default_path("fields.yaml")), type=Path)
        p.add_argument("--rules", default=str(_default_path("rules.yaml")), type=Path)

    read_p = sub.add_parser("read", help="show extracted fields for documents")
    common(read_p)

    process_p = sub.add_parser("process", help="print suggested decision per document")
    common(process_p)

    watch_p = sub.add_parser("watch", help="process every document in a directory")
    watch_p.add_argument("directory", type=Path)
    watch_p.add_argument("--fields", default=str(_default_path("fields.yaml")), type=Path)
    watch_p.add_argument("--rules", default=str(_default_path("rules.yaml")), type=Path)

    serve_p = sub.add_parser("serve", help="run the web UI and JSON API")
    serve_p.add_argument("--host", default="127.0.0.1")
    serve_p.add_argument("--port", type=int, default=8000)
    serve_p.add_argument("--fields", default=str(_default_path("fields.yaml")), type=Path)
    serve_p.add_argument("--rules", default=str(_default_path("rules.yaml")), type=Path)
    return parser


def _default_path(name: str) -> Path:
    return Path(__file__).resolve().parent.parent / name


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "serve":
        from .web import create_app

        try:
            application = create_app(Path(args.fields), Path(args.rules))
        except (OSError, ValueError) as exc:
            print(f"configuration error: {exc}", file=sys.stderr)
            return 2
        import uvicorn

        uvicorn.run(application, host=args.host, port=args.port)
        return 0

    try:
        field_specs = load_field_specs(Path(args.fields))
        engine = load_engine(Path(args.rules)) if args.command in ("process", "watch") else None
    except (OSError, ValueError) as exc:
        print(f"configuration error: {exc}", file=sys.stderr)
        return 2

    if args.command == "watch":
        directory = args.directory
        if not directory.is_dir():
            print(f"not a directory: {directory}", file=sys.stderr)
            return 2
        extensions = {".txt", ".md", ".json", ".pdf"}
        docs = sorted(p for p in directory.iterdir() if p.suffix.lower() in extensions)
        args.documents = docs

    errors = 0
    for path in args.documents:
        try:
            doc = _process(path, field_specs, engine)
        except (ReadError, OSError, ValueError) as exc:
            print(json.dumps({"source": str(path), "error": str(exc)}))
            errors += 1
            continue
        print(json.dumps(doc, ensure_ascii=False))
    return 1 if errors else 0


def _process(path: Path, field_specs: dict, engine: RuleEngine | None) -> dict:
    if engine is None:
        from .document import Document
        from .extract import extract_fields

        doc = extract_fields(Document.from_file(path), field_specs)
        return {"source": doc.source, "fields": doc.fields}
    _, decision = decide_document(path, engine, field_specs)
    result = decision.to_dict()
    result["source"] = str(path)
    return result


if __name__ == "__main__":
    raise SystemExit(main())
