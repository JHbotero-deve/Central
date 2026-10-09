from fastapi import FastAPI
from app.admin import router as admin_router

app = FastAPI(title="Product Analyzer Central API", version="1.0.0")
app.include_router(admin_router)

@app.get("/")
def root():
    return {"status": "online", "platform": "aliexpress", "discount_filter": ">=50%"}
