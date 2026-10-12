#!/usr/bin/env python3
"""Audit contractual de ingesta, rotación, enlaces e interfaz pública."""
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
API = (ROOT / "product-analyzer/app/api.py").read_text(encoding="utf-8-sig")
DB = (ROOT / "product-analyzer/app/db.py").read_text(encoding="utf-8-sig")
PUB = (ROOT / "product-analyzer/app/publications.py").read_text(encoding="utf-8-sig")
WORKER = (ROOT / "product-analyzer/app/main.py").read_text(encoding="utf-8-sig")
INGEST = (ROOT / "product-analyzer/app/ingest.py").read_text(encoding="utf-8-sig")
SHOP = (ROOT / "product-analyzer/frontend/tienda.html").read_text(encoding="utf-8-sig")
CARDS = (ROOT / "product-analyzer/frontend/tarjetas.html").read_text(encoding="utf-8-sig")


def check(condition, message):
    print(f"[{'PASS' if condition else 'FAIL'}] {message}")
    if not condition:
        sys.exit(1)


check("p.checkout_mode" not in API,
      "la ruta de afiliación no consulta una columna inexistente en PostgreSQL")
check("CATALOG_MIN_DISCOUNT_PCT" in API and "discount_percentage(" in API,
      "la publicación automática exige un descuento real configurable")
check("affiliate_url" in API and "mongo_image_id" in API,
      "la tarjeta conserva enlace monetizable e imagen persistida")
check("catalog_expired_after_48h" in API and "catalog_expires_at <= NOW()" in API and "catalog_rotation_deferred" not in API,
      "las ofertas se desactivan al cumplir 48 horas aunque falle la ingesta")
check("previous_price" in DB.split("INSERT INTO products", 1)[1].split("ON CONFLICT", 1)[0],
      "la ingesta persiste el precio original de la oferta")
check("WHERE p.is_active = TRUE AND p.is_blocked = FALSE AND (p.catalog_expires_at IS NULL OR p.catalog_expires_at > NOW()) {where}" in PUB,
      "el escaparate excluye productos bloqueados, inactivos o caducados")
check("CATALOG_SYNC_INTERVAL_SECONDS" in WORKER and "_error_detail(exc)" in WORKER,
      "el trabajador informa errores completos y permite configurar el intervalo")
check('class="card-title"' in SHOP and 'class="discount-badge"' in SHOP,
      "la tarjeta pública muestra título y porcentaje de descuento")
check('id="central-figma-card-v3"' not in SHOP,
      "no queda el bloque CSS que sobrescribía el marcado real de las tarjetas")
check('function preview(){const m=model();S.mountDetail($("preview"),{...m,links:{},fallback:""},0)' in CARDS,
      "la vista previa administrativa no abre enlaces externos")

check("p.catalog_expires_at IS NULL OR p.catalog_expires_at > NOW()" in API and "p.catalog_expires_at IS NULL OR p.catalog_expires_at > NOW()" in PUB,
      "las vistas y publicaciones respetan la caducidad de 48 horas")
check("p.current_price > 0" in API,
      "el radar y el catálogo administrativo excluyen productos sin precio real")
check("NULLIF(p.source_metadata->>'mongo_image_id', '')" in PUB and "COALESCE(pc.sale_price, p.current_price) > 0" in PUB,
      "el escaparate acepta imágenes Mongo persistidas y exige un precio numérico real")
check("p.is_active=TRUE AND p.is_blocked=FALSE AND COALESCE(pc.sale_price,p.current_price)>0" in API,
      "la ficha pública solo sirve publicaciones activas con precio verificable")


check("_REFRESH_RETRY_AFTER" in INGEST and "time.monotonic()" in INGEST and "reintento en 300 s" in INGEST,
      "la renovación OAuth fallida se limita temporalmente y no satura cada búsqueda")
check('payload.get("error") or payload.get("code")' in INGEST and "código={error_code}" in INGEST,
      "el registro OAuth informa el código de error sin revelar tokens")


AMAZON = (ROOT / "product-analyzer/app/amazon_api.py").read_text(encoding="utf-8-sig")
TELEGRAM = (ROOT / "product-analyzer/app/telegram_alert.py").read_text(encoding="utf-8-sig")

check("data = _public_search(query, limit)" in INGEST and "if not data.get(\"results\")" in INGEST,
      "Mercado Libre cae a búsqueda pública cuando la API bloquea o no devuelve resultados")
check("if not _AUTH_FAILURE:" in AMAZON and "se continúa con búsqueda pública" in AMAZON and "return _search_amazon_web(keywords, limit)" in AMAZON,
      "Amazon conserva la búsqueda pública cuando faltan o se rechazan credenciales API")
check("fetch_mercadolibre(term, limit=8)" in TELEGRAM and "upsert_product(conn, \"mercadolibre\", category, item)" in TELEGRAM,
      "el comando /buscar descubre productos externos y los guarda en el catálogo")

print("[PASS] Auditoría de contrato del catálogo completada.")
