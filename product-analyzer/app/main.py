import asyncio
import os
import uvicorn
from fastapi import FastAPI
from api import _sync_store_catalog

app = FastAPI(title="Central Catalog Worker", docs_url=None, redoc_url=None)

async def sync_catalog_loop():
    while True:
        try:
            result = await asyncio.to_thread(_sync_store_catalog)
            print({"event": "catalog_sync", "result": result}, flush=True)
        except Exception as exc:
            print({"event": "catalog_sync_failed", "error": str(exc)}, flush=True)
        await asyncio.sleep(7200)

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(sync_catalog_loop())

@app.get("/health")
def health():
    return {"status": "ok", "service": "central-worker"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8000")))
