"""ASGI entrypoint for Vercel's Python runtime."""
import sys
import traceback
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

try:
    from docdecision.web import app
except BaseException:
    traceback.print_exc(file=sys.stderr)
    raise

__all__ = ["app"]
