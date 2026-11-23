"""ASGI entrypoint for Vercel's Python runtime."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from docdecision.web import app

__all__ = ["app"]
