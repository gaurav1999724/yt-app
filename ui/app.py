"""Local dashboard — no login. Run: python -m ui"""

from __future__ import annotations

import traceback
from pathlib import Path

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from ui import services

ROOT = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(ROOT / "templates"))

app = FastAPI(title="YouTube Pipeline UI", docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=str(ROOT / "static")), name="static")


@app.api_route("/", methods=["GET", "HEAD"], response_class=HTMLResponse)
async def home(request: Request):
    # HEAD is required for Render health checks
    if request.method == "HEAD":
        return HTMLResponse(content="", status_code=200)
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "runs": services.list_runs(),
            "config": services.config_summary(),
        },
    )


@app.get("/runs/{run_id}", response_class=HTMLResponse)
async def run_page(request: Request, run_id: str):
    try:
        run = services.load_run(run_id)
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc
    from time import time

    return templates.TemplateResponse(
        request,
        "run.html",
        {
            "run": run,
            "config": services.config_summary(),
            "cache_bust": int(time()),
        },
    )


@app.post("/api/runs")
def api_create_run(
    idea: str = Form(...),
    script: str = Form(""),
    package_json: str = Form(""),
    seo_json: str = Form(""),
    broll_provider: str = Form("pixabay"),
):
    # Sync handlers run in a threadpool — safe for asyncio.run() inside TTS.
    try:
        run_id = services.create_run(
            idea, script, package_json, seo_json, broll_provider=broll_provider
        )
    except Exception as exc:  # noqa: BLE001
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)
    return {"ok": True, "run_id": run_id, "redirect": f"/runs/{run_id}"}


@app.post("/api/runs/{run_id}/save")
def api_save(
    run_id: str,
    script: str = Form(""),
    package_json: str = Form(""),
    seo_json: str = Form(""),
    broll_provider: str = Form(""),
):
    try:
        services.save_run_files(
            run_id, script, package_json, seo_json, broll_provider=broll_provider
        )
    except Exception as exc:  # noqa: BLE001
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)
    run = services.load_run(run_id)
    return {
        "ok": True,
        "status": run["status"],
        "broll_provider": run["broll_provider"],
    }


@app.post("/api/runs/{run_id}/render")
def api_render(run_id: str, broll_provider: str = Form("")):
    try:
        result = services.action_render(run_id, broll_provider=broll_provider)
    except Exception as exc:  # noqa: BLE001
        return JSONResponse(
            {"ok": False, "error": str(exc), "trace": traceback.format_exc()},
            status_code=500,
        )
    if not result.get("ok"):
        return JSONResponse(result, status_code=500)
    return result


@app.post("/api/runs/{run_id}/approve")
def api_approve(run_id: str):
    try:
        result = services.action_approve(run_id)
    except Exception as exc:  # noqa: BLE001
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)
    if not result["ok"]:
        return JSONResponse(
            {**result, "error": "Approve failed — render until READY_FOR_REVIEW first."},
            status_code=400,
        )
    return result


@app.post("/api/runs/{run_id}/upload")
def api_upload(run_id: str, privacy: str = Form(None)):
    try:
        result = services.action_upload(run_id, privacy=privacy or None)
    except Exception as exc:  # noqa: BLE001
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)
    if not result["ok"]:
        return JSONResponse(
            {
                **result,
                "error": "Upload failed — approve (ship it) first, and check YouTube OAuth.",
            },
            status_code=400,
        )
    return result


@app.get("/api/runs/{run_id}")
def api_run(run_id: str):
    try:
        return services.load_run(run_id)
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc


@app.get("/media/{run_id}/{name}")
def media(run_id: str, name: str):
    allowed = {
        "video.mp4": "video/mp4",
        "thumb.png": "image/png",
        "thumb.feed.png": "image/png",
        "audio.mp3": "audio/mpeg",
    }
    if name not in allowed:
        raise HTTPException(404, "Not found")
    try:
        path = services.run_dir(run_id) / name
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc
    if not path.exists():
        raise HTTPException(404, "File missing")
    return FileResponse(path, media_type=allowed[name])


def main() -> int:
    import os

    import uvicorn

    # Render injects PORT and expects 0.0.0.0 (not 127.0.0.1)
    port = int(os.environ.get("PORT", "8765"))
    host = os.environ.get("HOST", "0.0.0.0")
    print(f"YouTube Pipeline UI -> http://{host}:{port}")
    uvicorn.run("ui.app:app", host=host, port=port, reload=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
