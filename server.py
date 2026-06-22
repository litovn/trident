"""Local backend<->frontend bridge.

Serves the frontend and runs a real TRIDENT campaign per prompt, so the UI gets
backend data automatically (no manual file selection).

    pip install -e ".[sdk,ranker,real,bridge]"   # bridge + the campaign runtime
    python server.py                          # http://127.0.0.1:8000

Routes
------
GET  /            -> frontend/index.html with an injected <script src="/bridge.js">
GET  /bridge.js   -> the integration script (wraps the UI's launch hooks)
POST /api/run     -> {prompt, mode, target?} -> runs `python -m src.cli` and
                     returns the produced trace.jsonl as text
GET  /api/sample  -> the bundled sample trace (handy offline check)

A real run needs the campaign runtime (Copilot SDK + Foundry + `az login`).
Set TRIDENT_BRIDGE_DEMO=1 to short-circuit /api/run to the sample trace, which
exercises the full UI pipeline without Foundry.
"""
import json
import os
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, PlainTextResponse
import uvicorn

ROOT = Path(__file__).resolve().parent
FRONTEND = ROOT / "frontend"
SAMPLE = FRONTEND / "sample.trace.jsonl"

# Host allow-list per target (mirrors manifests/*.yaml). Empty => no host check.
HOST_ALLOWLIST: dict[str, list[str]] = {
    "echo": ["memory://echo", "127.0.0.1"],
    "aigoat": [],
}

app = FastAPI(title="TRIDENT bridge")


def _inject(html: str) -> str:
    tag = '<script src="/bridge.js"></script>'
    if tag in html:
        return html
    return html.replace("</body>", tag + "\n</body>", 1)


@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    return HTMLResponse(_inject((FRONTEND / "index.html").read_text(encoding="utf-8")))


@app.get("/bridge.js")
def bridge_js() -> FileResponse:
    return FileResponse(FRONTEND / "bridge.js", media_type="application/javascript")


@app.get("/api/sample", response_class=PlainTextResponse)
def sample() -> PlainTextResponse:
    return PlainTextResponse(SAMPLE.read_text(encoding="utf-8"))


@app.post("/api/run")
async def run(req: Request):
    body = await req.json()
    prompt = (body.get("prompt") or "").strip()
    mode = body.get("mode") if body.get("mode") in ("recon", "attack") else "attack"
    target = body.get("target") if body.get("target") in ("echo", "aigoat") \
        else os.environ.get("TRIDENT_TARGET", "echo")
    if not prompt:
        return JSONResponse({"ok": False, "error": "empty prompt"}, status_code=400)

    # Offline/demo path: exercise the whole UI pipeline without Foundry.
    if os.environ.get("TRIDENT_BRIDGE_DEMO") == "1":
        return {"ok": True, "source": "sample", "mode": mode,
                "trace": SAMPLE.read_text(encoding="utf-8")}

    out_dir = Path(tempfile.mkdtemp(prefix="trident-run-"))
    cid = "web-" + uuid.uuid4().hex[:8]
    manifest = out_dir / "manifest.yaml"
    manifest.write_text(
        f"campaign_id: {cid}\n"
        f"mode: {mode}\n"
        f"target_profile_id: {target}\n"
        f"technique_denylist: []\n"
        f"host_allowlist: {json.dumps(HOST_ALLOWLIST.get(target, []))}\n"
        f"query_budget_per_vertical: 20\n"
        f"hitl_techniques: []\n",
        encoding="utf-8",
    )
    cmd = [
        sys.executable, "-m", "src.cli",
        "--manifest", str(manifest),
        "--catalog", "catalog",
        "--targets-dir", "targets",
        "--out", str(out_dir),
        "--prompt", prompt,
    ]
    try:
        proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=600)
    except subprocess.TimeoutExpired:
        return JSONResponse({"ok": False, "error": "campaign timed out (600s)"}, status_code=504)

    trace_files = list(out_dir.glob("*.trace.jsonl"))
    if proc.returncode != 0 or not trace_files:
        return JSONResponse(
            {"ok": False, "error": "campaign failed — is the campaign runtime installed "
                                   "and Foundry configured? (pip install -e \".[sdk,ranker,real]\" + az login)",
             "detail": (proc.stderr or proc.stdout or "")[-2000:]},
            status_code=500,
        )
    return {"ok": True, "source": "live", "mode": mode, "campaign_id": cid,
            "trace": trace_files[0].read_text(encoding="utf-8")}


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=int(os.environ.get("PORT", "8000")))
