"""MongoDB secundario: auditoría y telemetría no crítica.
PostgreSQL sigue siendo la fuente de verdad transaccional de Central.
Si Mongo falla, autenticación, tienda y pipeline continúan operativos.
"""
import os
from datetime import datetime, timezone

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
        return {"configured": True, "connected": True}
    except Exception as exc:
        return {"configured": True, "connected": False, "error": str(exc)[:180]}
