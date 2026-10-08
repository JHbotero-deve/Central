"""Autenticacion y autorizacion de Central."""
import base64
import hashlib
import hmac
import json
import os
import secrets
import smtplib
import ssl
import time
from email.message import EmailMessage
from typing import Any

from fastapi import APIRouter, Cookie, Depends, Header, HTTPException, Response
from pydantic import BaseModel, Field
from db import get_connection
from mongo_store import audit_event

router = APIRouter(prefix="/auth", tags=["auth"])
TOKEN_TTL_SECONDS = 8 * 60 * 60
AUTH_COOKIE = "central_session"
MAX_FAILED_LOGINS = 8
PBKDF2_ROUNDS = 310_000
RESET_TTL_SECONDS = 30 * 60

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

def _ensure_reset_table() -> None:
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS central_password_resets (
                    id BIGSERIAL PRIMARY KEY,
                    user_id BIGINT NOT NULL REFERENCES central_users(id) ON DELETE CASCADE,
                    token_hash TEXT NOT NULL UNIQUE,
                    expires_at TIMESTAMPTZ NOT NULL,
                    used_at TIMESTAMPTZ,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
            """)
        conn.commit()
    finally:
        conn.close()

def _send_reset_email(email: str, reset_url: str) -> None:
    host = os.getenv("CENTRAL_SMTP_HOST", "").strip()
    port = int(os.getenv("CENTRAL_SMTP_PORT", "587") or "587")
    username = os.getenv("CENTRAL_SMTP_USER", "").strip()
    password = os.getenv("CENTRAL_SMTP_PASSWORD", "")
    sender = os.getenv("CENTRAL_SMTP_FROM", username).strip()
    if not host or not username or not password or not sender:
        raise HTTPException(status_code=503, detail="Correo de recuperacion no configurado")
    msg = EmailMessage()
    msg["Subject"] = "Central — Recuperación de contraseña"
    msg["From"] = sender
    msg["To"] = email
    msg.set_content(f"Solicitaste recuperar tu contraseña de Central.\n\nAbre este enlace para crear una nueva contraseña:\n{reset_url}\n\nEl enlace vence en 30 minutos. Si no solicitaste el cambio, ignora este mensaje.")
    context = ssl.create_default_context()
    if port == 465:
        with smtplib.SMTP_SSL(host, port, context=context, timeout=20) as smtp:
            smtp.login(username, password)
            smtp.send_message(msg)
    else:
        with smtplib.SMTP(host, port, timeout=20) as smtp:
            smtp.starttls(context=context)
            smtp.login(username, password)
            smtp.send_message(msg)

def _hash_reset_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()

def _app_url() -> str:
    return os.getenv("CENTRAL_APP_URL", "https://central-7ykr.vercel.app").strip().rstrip("/")

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
def login(payload: LoginPayload, response: Response):
    _ensure_auth_table()
    email = payload.email.strip().lower()
    if "@" not in email or len(email) > 320:
        raise HTTPException(status_code=422, detail="Correo invalido")
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS central_login_attempts (
                    id BIGSERIAL PRIMARY KEY,
                    email TEXT NOT NULL,
                    success BOOLEAN NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
            """)
            cur.execute("""
                SELECT COUNT(*) AS failures FROM central_login_attempts
                WHERE email=%s AND success=FALSE
                  AND created_at >= NOW() - INTERVAL '15 minutes'
            """, (email,))
            if int(cur.fetchone()["failures"] or 0) >= MAX_FAILED_LOGINS:
                raise HTTPException(status_code=429, detail="Demasiados intentos. Espere 15 minutos.")
            cur.execute("SELECT COUNT(*) AS total FROM central_users")
            user_count = int(cur.fetchone()["total"] or 0)
            cur.execute("SELECT id,email,password_hash,role,is_active FROM central_users WHERE email=%s", (email,))
            user = cur.fetchone()
        conn.commit()
    finally:
        conn.close()
    if not user:
        if user_count > 0:
            audit_event("login_failure", email=email)
            raise HTTPException(status_code=401, detail="Credenciales invalidas")
        try:
            _bootstrap_admin(email, payload.password)
        except HTTPException:
            audit_event("login_failure", email=email)
            conn = get_connection()
            try:
                with conn.cursor() as cur:
                    cur.execute("INSERT INTO central_login_attempts(email,success) VALUES (%s,FALSE)", (email,))
                conn.commit()
            finally:
                conn.close()
            raise HTTPException(status_code=401, detail="Credenciales invalidas")
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT id,email,password_hash,role,is_active FROM central_users WHERE email=%s", (email,))
                user = cur.fetchone()
        finally:
            conn.close()
    if not user or not user["is_active"] or not verify_password(payload.password, user["password_hash"]):
        audit_event("login_failure", email=email)
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("INSERT INTO central_login_attempts(email,success) VALUES (%s,FALSE)", (email,))
            conn.commit()
        finally:
            conn.close()
        raise HTTPException(status_code=401, detail="Credenciales invalidas")
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("INSERT INTO central_login_attempts(email,success) VALUES (%s,TRUE)", (email,))
        conn.commit()
    finally:
        conn.close()
    now = int(time.time())
    token = _sign(
        {"alg": "HS256", "typ": "JWT"},
        {"iss": "central", "sub": str(user["id"]), "email": user["email"], "role": user["role"], "iat": now, "exp": now + TOKEN_TTL_SECONDS},
    )
    response.set_cookie(AUTH_COOKIE, token, max_age=TOKEN_TTL_SECONDS, httponly=True, secure=True, samesite="none", path="/")
    audit_event("login_success", email=user["email"], role=user["role"])
    return {"access_token": token, "token_type": "bearer", "expires_in": TOKEN_TTL_SECONDS,
            "user": {"id": user["id"], "email": user["email"], "role": user["role"]}}

@router.post("/logout")
def logout(response: Response):
    response.delete_cookie(AUTH_COOKIE, path="/")
    return {"ok": True}

class PasswordResetRequest(BaseModel):
    email: str

class PasswordResetConfirm(BaseModel):
    token: str = Field(min_length=32, max_length=128)
    new_password: str = Field(min_length=12, max_length=256)

@router.post("/password/forgot")
def forgot_password(payload: PasswordResetRequest):
    _ensure_auth_table()
    _ensure_reset_table()
    email = payload.email.strip().lower()
    generic = {"ok": True, "message": "Si el correo existe, recibirás un enlace para recuperar la contraseña."}
    if "@" not in email or len(email) > 320:
        return generic
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id,email,is_active FROM central_users WHERE email=%s", (email,))
            user = cur.fetchone()
            if not user or not user["is_active"]:
                return generic
            token = secrets.token_urlsafe(48)
            cur.execute("UPDATE central_password_resets SET used_at=NOW() WHERE user_id=%s AND used_at IS NULL", (user["id"],))
            cur.execute("INSERT INTO central_password_resets(user_id,token_hash,expires_at) VALUES (%s,%s,NOW()+INTERVAL '30 minutes')", (user["id"], _hash_reset_token(token)))
        conn.commit()
    finally:
        conn.close()
    try:
        _send_reset_email(email, f"{_app_url()}/recuperar-contrasena?token={token}")
    except Exception:
        audit_event("password_reset_email_failure", email=email)
        raise HTTPException(status_code=503, detail="No fue posible enviar el correo de recuperacion")
    audit_event("password_reset_requested", email=email)
    return generic

@router.post("/password/reset")
def reset_password(payload: PasswordResetConfirm):
    _ensure_auth_table()
    _ensure_reset_table()
    token_hash = _hash_reset_token(payload.token)
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT r.id,r.user_id,u.email
                FROM central_password_resets r
                JOIN central_users u ON u.id=r.user_id
                WHERE r.token_hash=%s AND r.used_at IS NULL AND r.expires_at>NOW() AND u.is_active=TRUE
            """, (token_hash,))
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=400, detail="Enlace invalido o expirado")
            cur.execute("UPDATE central_users SET password_hash=%s,updated_at=NOW() WHERE id=%s", (hash_password(payload.new_password), row["user_id"]))
            cur.execute("UPDATE central_password_resets SET used_at=NOW() WHERE id=%s", (row["id"],))
        conn.commit()
    finally:
        conn.close()
    audit_event("password_reset_completed", user_id=row["user_id"], email=row["email"])
    return {"ok": True}

def current_user(
    authorization: str | None = Header(default=None),
    central_session: str | None = Cookie(default=None, alias=AUTH_COOKIE),
) -> dict[str, Any]:
    if authorization and authorization.lower().startswith("bearer "):
        return _decode(authorization[7:].strip())
    if central_session:
        return _decode(central_session)
    raise HTTPException(status_code=401, detail="Autenticacion requerida")

def require_admin(user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Permisos insuficientes")
    return user

def require_operator(user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    if user.get("role") not in {"admin", "operator"}:
        raise HTTPException(status_code=403, detail="Permisos insuficientes")
    return user

class PasswordChange(BaseModel):
    current_password: str = Field(min_length=8, max_length=256)
    new_password: str = Field(min_length=12, max_length=256)

@router.post("/password")
def change_password(payload: PasswordChange, user: dict[str, Any] = Depends(require_admin)):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT password_hash FROM central_users WHERE id=%s AND is_active=TRUE", (user.get("sub"),))
            row = cur.fetchone()
            if not row or not verify_password(payload.current_password, row["password_hash"]):
                raise HTTPException(status_code=401, detail="Contraseña actual invalida")
            cur.execute(
                "UPDATE central_users SET password_hash=%s, updated_at=NOW() WHERE id=%s",
                (hash_password(payload.new_password), user.get("sub")),
            )
        conn.commit()
    finally:
        conn.close()
    audit_event("password_changed", user_id=user.get("sub"), email=user.get("email"))
    return {"ok": True}

@router.get("/me")
def me(user: dict[str, Any] = Depends(current_user)):
    return {"id": user.get("sub"), "email": user.get("email"), "role": user.get("role")}

def init_auth() -> None:
    _ensure_auth_table()
