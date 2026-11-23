from __future__ import annotations

import re
from pathlib import Path

from .document import Document


def extract_fields(doc: Document, field_specs: dict) -> Document:
    for name, spec in field_specs.items():
        pattern = str(spec["regex"])
        cast = str(spec.get("cast", "string"))
        match = re.search(pattern, doc.text, flags=re.IGNORECASE)
        if not match:
            continue
        value = match.groupdict().get("value", match.group(0))
        doc.fields[name] = _cast(value, cast)
    return doc


def _cast(value, cast: str):
    if value is None:
        return None
    text = value.replace(",", "") if cast in ("number", "float") else value
    try:
        if cast == "number":
            return int(text)
        if cast == "float":
            return float(text)
    except (TypeError, ValueError):
        return None
    return text.strip()


def load_field_specs(path: Path) -> dict:
    import yaml

    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return data.get("fields", {})
