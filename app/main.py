"""Local HTTP server: static plate plus a small JSON API."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import config
from .store import load_history, load_latest_json

app = FastAPI(title="Hyperliquid BTC consensus", docs_url=None, redoc_url=None)


@app.get("/api/signal")
def api_signal():
    payload = load_latest_json()
    if payload is None:
        return JSONResponse(
            {"error": "No snapshot yet. Run python -m app.sweep first."},
            status_code=404,
        )
    return payload


@app.get("/api/history")
def api_history():
    return load_history()


@app.get("/")
def index():
    return FileResponse(config.SITE_DIR / "index.html")


app.mount("/data", StaticFiles(directory=str(config.SITE_DATA_DIR)), name="data")
app.mount("/", StaticFiles(directory=str(config.SITE_DIR), html=True), name="site")


def run() -> None:
    import uvicorn

    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=False)


if __name__ == "__main__":
    run()
