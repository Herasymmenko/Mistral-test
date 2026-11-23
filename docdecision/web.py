"""Web UI and JSON API wrapping the document decision pipeline."""
from __future__ import annotations

import tempfile
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import HTMLResponse

from .decision import decide_document
from .document import ReadError
from .extract import load_field_specs
from .rules import load_engine

PROJECT_ROOT = Path(__file__).resolve().parents[1]

PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>docdecision</title>
<style>
  :root { color-scheme: light dark; font-family: system-ui, sans-serif; }
  body { max-width: 720px; margin: 2rem auto; padding: 0 1rem; }
  h1 { font-size: 1.4rem; }
  #drop { border: 2px dashed gray; border-radius: 8px; padding: 2.5rem; text-align: center; cursor: pointer; }
  #drop.drag { border-color: Highlight; background: color-mix(in srgb, Highlight 10%, transparent); }
  .verdict { margin-top: 1.5rem; padding: 1rem; border: 1px solid gray; border-radius: 8px; }
  .badge { display: inline-block; padding: .15rem .6rem; border-radius: 999px; color: white; font-weight: 600; }
  .approve { background: #1a7f37; } .escalate { background: #cf222e; }
  .review { background: #9a6700; } .request_more_info { background: #57606a; }
  .needs_review { background: #57606a; }
  ul { margin: .4rem 0; } table { border-collapse: collapse; margin-top: .5rem; }
  td, th { border: 1px solid gray; padding: .25rem .6rem; text-align: left; }
  .error { color: #cf222e; white-space: pre-wrap; }
</style>
</head>
<body>
<h1>Document decision</h1>
<p>Upload an incoming document (.txt, .md, .json, .pdf) and get a suggested decision.</p>
<div id="drop">Drop a file here or <input id="file" type="file" accept=".txt,.md,.json,.pdf"></div>
<div id="result"></div>
<script>
const drop = document.getElementById("drop");
const fileInput = document.getElementById("file");
const result = document.getElementById("result");

drop.addEventListener("click", () => fileInput.click());
drop.addEventListener("dragover", e => { e.preventDefault(); drop.classList.add("drag"); });
drop.addEventListener("dragleave", () => drop.classList.remove("drag"));
drop.addEventListener("drop", e => { e.preventDefault(); drop.classList.remove("drag"); submit(e.dataTransfer.files[0]); });
fileInput.addEventListener("change", () => { if (fileInput.files[0]) submit(fileInput.files[0]); });

async function submit(file) {
  result.innerHTML = "<p>Processing&hellip;</p>";
  try {
    const response = await fetch("/decide", { method: "POST", body: buildBody(file) });
    const payload = await response.json();
    response.ok ? render(file.name, payload) : showError(payload.detail ?? JSON.stringify(payload));
  } catch (err) { showError(String(err)); }
  fileInput.value = "";
}

function buildBody(file) {
  const body = new FormData();
  body.append("file", file);
  return body;
}

function render(name, d) {
  const fields = Object.entries(d.fields ?? {})
    .map(([k, v]) => `<tr><th>${escapeHtml(k)}</th><td>${escapeHtml(String(v))}</td></tr>`).join("");
  const reasons = (d.reasons ?? []).map(r => `<li>${escapeHtml(r)}</li>`).join("");
  result.innerHTML = `
    <div class="verdict">
      <span class="badge ${d.decision}">${escapeHtml(d.decision)}</span>
      <strong> ${escapeHtml(name)}</strong>
      <p>rule: ${d.rule ? escapeHtml(d.rule) : "<em>none matched</em>"}</p>
      <ul>${reasons}</ul>
      ${fields ? `<table>${fields}</table>` : ""}
    </div>`;
}

function showError(message) {
  result.innerHTML = `<p class="error">Failed: ${escapeHtml(String(message))}</p>`;
}

function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}
</script>
</body>
</html>
"""


def create_app(fields_path: Path | None = None, rules_path: Path | None = None) -> FastAPI:
    fields_path = Path(fields_path) if fields_path else PROJECT_ROOT / "fields.yaml"
    rules_path = Path(rules_path) if rules_path else PROJECT_ROOT / "rules.yaml"

    app = FastAPI(title="docdecision", version="0.2.0", docs_url="/docs")
    state: dict = {}

    def engine():
        if "engine" not in state:
            state["engine"] = load_engine(rules_path)
        return state["engine"]

    def specs():
        if "specs" not in state:
            state["specs"] = load_field_specs(fields_path)
        return state["specs"]

    async def decide(file: UploadFile = File(...)):
        tmp_dir = Path(tempfile.mkdtemp(prefix="docdecision-"))
        tmp_path = tmp_dir / Path(file.filename or "document").name
        tmp_path.write_bytes(await file.read())
        try:
            _, decision = decide_document(tmp_path, engine(), specs())
        except (ReadError, OSError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        finally:
            tmp_path.unlink(missing_ok=True)
            tmp_dir.rmdir()
        result = decision.to_dict()
        result["source"] = file.filename
        return result

    def health():
        return {"status": "ok"}

    def index():
        return HTMLResponse(PAGE)

    app.add_api_route("/decide", decide, methods=["POST"], name="decide")
    app.add_api_route("/api/decide", decide, methods=["POST"], name="decide_api")
    app.add_api_route("/health", health, methods=["GET"], name="health")
    app.add_api_route("/", index, methods=["GET"], include_in_schema=False, name="index")
    return app


app = create_app()
