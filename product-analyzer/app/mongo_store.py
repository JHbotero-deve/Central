"""MongoDB secundario: auditoría y telemetría no crítica.
PostgreSQL sigue siendo la fuente de verdad transaccional de Central.
Si Mongo falla, autenticación, tienda y pipeline continúan operativos.
"""
import os
from datetime import datetime, timezone
from bson import Binary, ObjectId
import hashlib
import requests

_client = None
_db = None

def _get_db():
    global _client, _db
    uri = (os.getenv("MONGO_URL") or "").strip()
    if not uri:
        return None
    if _db is None:
        from pymongo import MongoClient
        _client = MongoClient(uri, serverSelectionTimeoutMS=2500, connectTimeoutMS=2500)
        _db = _client[os.getenv("MONGO_DB_NAME", "central")]
    return _db

def store_product_image(url: str, **metadata):
    url = (url or "").strip()
    if not url:
        return None
    db = _get_db()
    if db is None:
        return None
    response = requests.get(url, headers={"User-Agent": "CentralMedia/1.0"}, timeout=15, allow_redirects=True)
    response.raise_for_status()
    content_type = (response.headers.get("Content-Type") or "").split(";", 1)[0].lower()
    if content_type not in {"image/jpeg","image/png","image/webp","image/gif","image/avif","image/svg+xml"}:
        raise ValueError("recurso no es imagen")
    data = response.content
    if not data or len(data) > 8 * 1024 * 1024:
        raise ValueError("imagen vacía o mayor de 8 MB")
    digest = hashlib.sha256(data).hexdigest()
    found = db.product_images.find_one({"sha256": digest}, {"_id": 1})
    if found:
        return str(found["_id"])
    doc = {"data": Binary(data), "content_type": content_type, "sha256": digest,
           "original_url": url[:2000], "created_at": datetime.now(timezone.utc), **metadata}
    return str(db.product_images.insert_one(doc).inserted_id)

def read_product_image(file_id: str):
    db = _get_db()
    if db is None:
        return None, None
    try:
        doc = db.product_images.find_one({"_id": ObjectId(str(file_id))})
        if not doc:
            return None, None
        return bytes(doc.get("data") or b""), doc.get("content_type") or "application/octet-stream"
    except Exception:
        return None, None

def audit_event(event: str, **data):
    try:
        db = _get_db()
        if db is None:
            return False
        doc = {
            "event": event,
            "created_at": datetime.now(timezone.utc),
            "data": data,
        }
        db.security_audit.insert_one(doc)
        return True
    except Exception as exc:
        print(f"[mongo] auditoría no disponible: {exc}")
        return False

def health():
    try:
        db = _get_db()
        if db is None:
            return {"configured": False, "connected": False}
        db.command("ping")
        return {"configured": True, "connected": True, "images": db.product_images.count_documents({})}
    except Exception as exc:
        return {"configured": True, "connected": False, "error": str(exc)[:180]}
