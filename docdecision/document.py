from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


class ReadError(Exception):
    """Raised when a document cannot be read or parsed."""


@dataclass
class Document:
    source: str
    text: str
    fields: dict = field(default_factory=dict)

    @classmethod
    def from_file(cls, path: Path) -> "Document":
        suffix = path.suffix.lower()
        readers = {
            ".txt": cls._read_text,
            ".md": cls._read_text,
            ".json": cls._read_json,
            ".pdf": cls._read_pdf,
        }
        reader = readers.get(suffix)
        if reader is None:
            raise ReadError(f"unsupported document type: {path.name}")
        text = reader(path)
        return cls(source=str(path), text=text)

    @staticmethod
    def _read_text(path: Path) -> str:
        try:
            return path.read_text(encoding="utf-8")
        except OSError as exc:
            raise ReadError(f"cannot read {path.name}: {exc}") from exc

    @staticmethod
    def _read_json(path: Path) -> str:
        text = Document._read_text(path)
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ReadError(f"{path.name} is not valid JSON: {exc}") from exc
        if not isinstance(data, dict):
            raise ReadError(f"{path.name} must contain a JSON object")
        return "\n".join(
            f"{key}: {value}" for key, value in data.items() if value is not None
        )

    @staticmethod
    def _read_pdf(path: Path) -> str:
        try:
            from pypdf import PdfReader
        except ImportError as exc:
            raise ReadError(
                f"PDF support for {path.name} requires pypdf; "
                "install with: pip install 'docdecision[pdf]'"
            ) from exc
        try:
            reader = PdfReader(str(path))
            return "\n".join(page.extract_text() or "" for page in reader.pages)
        except Exception as exc:
            raise ReadError(f"cannot parse {path.name}: {exc}") from exc
