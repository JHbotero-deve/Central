"""Autenticacion y autorizacion de Central."""
import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from db import get_connection

router = APIRouter(prefix="/auth", tags=["auth"])
TOKEN_TTL_SECONDS = 8 * 60 * 60
PBKDF2_ROUNDS = 310_000

class LoginPayload(BaseModel):
    email: str
    password: str = Field(min_length=8, max_length=256)

def _secret() -> bytes:
    value = os.getenv("CENTRAL_AUTH_SECRET", "").strip()
    if len(value) < 32:
        raise HTTPException(status_code=503, detail="Autenticacion no configurada")
    return value.encode()

def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode()

def _unb64(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))

def hash_password(password: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, PBKDF2_ROUNDS)
    return "pbkdf2_sha256$" + str(PBKDF2_ROUNDS) + "$" + _b64(salt) + "$" + _b64(digest)

def verify_password(password: str, encoded: str) -> bool:
    try:
        scheme, rounds, salt, expected = encoded.split("$", 3)
        if scheme != "pbkdf2_sha256":
            return False
        digest = hashlib.pbkdf2_hmac("sha256", password.encode(), _unb64(salt), int(rounds))
        return hmac.compare_digest(_b64(digest), expected)
    except (ValueError, TypeError):
        return False

def _sign(header: dict[str, Any], payload: dict[str, Any]) -> str:
    head = _b64(json.dumps(header, separators=(",", ":")).encode())
    body = _b64(json.dumps(payload, separators=(",", ":")).encode())
    signed = head + "." + body
    signature = hmac.new(_secret(), signed.encode(), hashlib.sha256).digest()
    return signed + "." + _b64(signature)

def _decode(token: str) -> dict[str, Any]:
    try:
        head, body, signature = token.split(".", 2)
        signed = head + "." + body
        expected = hmac.new(_secret(), signed.encode(), hashlib.sha256).digest()
        if not hmac.compare_digest(_unb64(signature), expected):
            raise HTTPException(status_code=401, detail="Token invalido")
        payload = json.loads(_unb64(body))
        if payload.get("exp", 0) < int(time.time()) or payload.get("iss") != "central":
            raise HTTPException(status_code=401, detail="Token invalido o expirado")
        return payload
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Token invalido") from exc

def _legacy_admin(x_admin_key: str | None) -> bool:
    values = [os.getenv("ADMIN_API_KEY", "").strip(), os.getenv("MONETIZATION_ADMIN_KEY", "").strip()]
    return bool(x_admin_key) and any(v and hmac.compare_digest(x_admin_key, v) for v in values)

def _ensure_auth_table() -> None:
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS central_users (
                    id BIGSERIAL PRIMARY KEY,
                    email TEXT NOT NULL UNIQUE,
                    password_hash TEXT NOT NULL,
                    role TEXT NOT NULL DEFAULT 'operator' CHECK (role IN ('admin','operator')),
                    is_active BOOLEAN NOT NULL DEFAULT TRUE,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
            """)
        conn.commit()
    finally:
        conn.close()

def _bootstrap_admin(email: str, password: str) -> None:
    bootstrap_email = os.getenv("CENTRAL_ADMIN_EMAIL", "").strip().lower()
    bootstrap_password = os.getenv("CENTRAL_ADMIN_PASSWORD", "")
    if not bootstrap_email or not bootstrap_password:
        raise HTTPException(status_code=503, detail="Administrador inicial no configurado")
    if not hmac.compare_digest(email, bootstrap_email) or not hmac.compare_digest(password, bootstrap_password):
        raise HTTPException(status_code=401, detail="Credenciales invalidas")
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO central_users(email,password_hash,role) VALUES (%s,%s,'admin') ON CONFLICT (email) DO NOTHING",
                (email, hash_password(password)),
            )
        conn.commit()
    finally:
        conn.close()

@router.post("/login")
def login(payload: LoginPayload):
    _ensure_auth_table()
    email = payload.email.strip().lower()
    if "@" not in email or len(email) > 320:
        raise HTTPException(status_code=422, detail="Correo invalido")
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id,email,password_hash,role,is_active FROM central_users WHERE email=%s", (email,))
            user = cur.fetchone()
    finally:
        conn.close()
    if not user:
        _bootstrap_admin(email, payload.password)
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT id,email,password_hash,role,is_active FROM central_users WHERE email=%s", (email,))
                user = cur.fetchone()
        finally:
            conn.close()
    if not user or not user["is_active"] or not verify_password(payload.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Credenciales invalidas")
    now = int(time.time())
    token = _sign(
        {"alg": "HS256", "typ": "JWT"},
        {"iss": "central", "sub": str(user["id"]), "email": user["email"], "role": user["role"], "iat": now, "exp": now + TOKEN_TTL_SECONDS},
    )
    return {"access_token": token, "token_type": "bearer", "expires_in": TOKEN_TTL_SECONDS, "user": {"id": user["id"], "email": user["email"], "role": user["role"]}}

def current_user(authorization: str | None = Header(default=None), x_admin_key: str | None = Header(default=None, alias="X-Admin-Key")) -> dict[str, Any]:
    if authorization and authorization.lower().startswith("bearer "):
        return _decode(authorization[7:].strip())
    if _legacy_admin(x_admin_key):
        return {"sub": "legacy-admin", "email": "legacy-admin", "role": "admin"}
    raise HTTPException(status_code=401, detail="Autenticacion requerida")

def require_admin(user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Permisos insuficientes")
    return user

def require_operator(user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    if user.get("role") not in {"admin", "operator"}:
        raise HTTPException(status_code=403, detail="Permisos insuficientes")
    return user

@router.get("/me")
def me(user: dict[str, Any] = Depends(current_user)):
    return {"id": user.get("sub"), "email": user.get("email"), "role": user.get("role")}

def init_auth() -> None:
    _ensure_auth_table()
