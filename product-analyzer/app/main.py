import asyncio
import os
import uvicorn
from fastapi import FastAPI, HTTPException
from api import _sync_store_catalog

app = FastAPI(title="Central Catalog Worker", docs_url=None, redoc_url=None)


def _error_detail(exc: Exception):
    """HTTPException convierte str(exc) en vacío; conservar el diagnóstico completo."""
    detail = getattr(exc, "detail", None)
    if detail is not None:
        return detail
    return {"type": type(exc).__name__, "message": str(exc) or repr(exc)}


async def sync_catalog_loop():
    interval = max(300, int(os.getenv("CATALOG_SYNC_INTERVAL_SECONDS", "7200")))
    print({"event": "catalog_worker_started", "interval_seconds": interval}, flush=True)
    while True:
        try:
            result = await asyncio.to_thread(_sync_store_catalog)
            print({"event": "catalog_sync", "result": result}, flush=True)
        except Exception as exc:
            print({"event": "catalog_sync_failed", "error": _error_detail(exc)}, flush=True)
        await asyncio.sleep(interval)


@app.on_event("startup")
async def startup_event():
    asyncio.create_task(sync_catalog_loop())


@app.get("/health")
def health():
    return {"status": "ok", "service": "central-worker"}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8000")))