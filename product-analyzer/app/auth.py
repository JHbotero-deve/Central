import base64
import hashlib
import hmac
import os
import secrets
import time
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Request, Response
from pydantic import BaseModel, Field

from db import get_connection

router = APIRouter(prefix="/auth", tags=["authentication"])
COOKIE = "central_admin_session"
TTL = 604800
ITERATIONS = 310000


class Credentials(BaseModel):
    email: str = Field(min_length=5, max_length=254)
    password: str = Field(min_length=1, max_length=256)


def _secret():
    secret = os.getenv("CENTRAL_AUTH_SECRET", "")
    if len(secret) < 32:
        raise HTTPException(503, "Autenticación no configurada")
    return secret.encode()


def _table(cur):
    cur.execute(
        "CREATE TABLE IF NOT EXISTS central_admin_auth "
        "(id SMALLINT PRIMARY KEY CHECK(id=1), email TEXT NOT NULL, "
        "password_hash TEXT NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW())"
    )


def _hash(password):
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, ITERATIONS)
    enc = lambda value: base64.urlsafe_b64encode(value).decode().rstrip("=")
    return "pbkdf2_sha256$" + str(ITERATIONS) + "$" + enc(salt) + "$" + enc(digest)


def _verify(password, encoded):
    try:
        algorithm, iterations, salt, digest = encoded.split("$", 3)
        dec = lambda value: base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
        candidate = hashlib.pbkdf2_hmac("sha256", password.encode(), dec(salt), int(iterations))
        return algorithm == "pbkdf2_sha256" and hmac.compare_digest(candidate, dec(digest))
    except Exception:
        return False


def _record():
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            _table(cur)
            cur.execute("SELECT email,password_hash FROM central_admin_auth WHERE id=1")
            row = cur.fetchone()
            if not row:
                email = os.getenv("CENTRAL_ADMIN_EMAIL", "").strip().lower()
                password = os.getenv("CENTRAL_ADMIN_PASSWORD", "")
                if email and len(password) >= 12:
                    cur.execute("SELECT pg_advisory_xact_lock(92483922)")
                    cur.execute("SELECT email,password_hash FROM central_admin_auth WHERE id=1")
                    row = cur.fetchone()
                    if not row:
                        cur.execute(
                            "INSERT INTO central_admin_auth(id,email,password_hash) VALUES(1,%s,%s)",
                            (email, _hash(password)),
                        )
                        cur.execute("SELECT email,password_hash FROM central_admin_auth WHERE id=1")
                        row = cur.fetchone()
        conn.commit()
        return row
    finally:
        conn.close()


def is_authenticated(request: Request):
    try:
        payload, signature = request.cookies[COOKIE].rsplit(".", 1)
        expected = hmac.new(_secret(), payload.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected):
            return False
        raw = base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)).decode()
        email, expires = raw.rsplit("|", 1)
        record = _record()
        return (
            int(expires) >= int(time.time())
            and bool(record)
            and hmac.compare_digest(email.lower(), record["email"].lower())
        )
    except Exception:
        return False


def require_admin(
    request: Request,
    x_admin_key: Optional[str] = Header(default=None, alias="X-Admin-Key"),
):
    if is_authenticated(request):
        return {"admin": True}
    expected = os.getenv("ADMIN_API_KEY", "")
    if expected and x_admin_key and hmac.compare_digest(expected, x_admin_key):
        return {"admin": True}
    raise HTTPException(401, "Inicia sesión para administrar Central")


def _session(response, email):
    expiry = int(time.time()) + TTL
    payload = base64.urlsafe_b64encode((email.lower() + "|" + str(expiry)).encode()).decode().rstrip("=")
    signature = hmac.new(_secret(), payload.encode(), hashlib.sha256).hexdigest()
    response.set_cookie(
        COOKIE,
        payload + "." + signature,
        max_age=TTL,
        httponly=True,
        secure=True,
        samesite="lax",
        path="/",
    )


@router.get("/status")
def status(request: Request):
    record = _record()
    authenticated = bool(record) and is_authenticated(request)
    return {
        "configured": bool(record),
        "setupRequired": False,
        "authenticated": authenticated,
        "email": record["email"] if authenticated else None,
    }


@router.post("/login")
def login(data: Credentials, response: Response):
    record = _record()
    if not record:
        raise HTTPException(
            503,
            "Acceso administrativo no configurado. Verifica CENTRAL_ADMIN_EMAIL y CENTRAL_ADMIN_PASSWORD en Railway.",
        )
    if (
        not hmac.compare_digest(data.email.strip().lower(), record["email"].lower())
        or not _verify(data.password, record["password_hash"])
    ):
        raise HTTPException(401, "Correo o contraseña incorrectos")
    _session(response, record["email"])
    return {"ok": True}


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie(COOKIE, path="/", secure=True, httponly=True, samesite="lax")
    return {"ok": True}
