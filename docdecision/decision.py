from __future__ import annotations

from pathlib import Path

from .document import Document, ReadError
from .extract import extract_fields
from .rules import Decision, RuleEngine


def decide_document(path: Path, engine: RuleEngine, field_specs: dict) -> tuple[Document, Decision]:
    doc = Document.from_file(path)
    extract_fields(doc, field_specs)
    return doc, engine.decide(doc.fields)
