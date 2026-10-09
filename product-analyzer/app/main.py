import asyncio
from fastapi import FastAPI
from app.admin import router as admin_router
from app.ingest import purge_expired_products

app = FastAPI(title="Product Analyzer Multiplatform Central", version="2.0.0")
app.include_router(admin_router)

async def background_sync_worker():
    while True:
        try:
            purge_expired_products()
        except Exception:
            pass
        await asyncio.sleep(7200)

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(background_sync_worker())

@app.get("/")
def root():
    return {"status": "online", "platforms": ["amazon", "mercadolibre", "aliexpress"], "discount_filter": ">=50%"}
