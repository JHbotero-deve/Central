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
check("catalog_rotation_deferred" in API and "catalog_expired_after_replacement" in API,
      "la caducidad se difiere si no hay reemplazos verificados")
check("previous_price" in DB.split("INSERT INTO products", 1)[1].split("ON CONFLICT", 1)[0],
      "la ingesta persiste el precio original de la oferta")
check("WHERE p.is_active = TRUE {where}" in PUB,
      "las ofertas vencidas se conservan visibles hasta una rotación segura")
check("CATALOG_SYNC_INTERVAL_SECONDS" in WORKER and "_error_detail(exc)" in WORKER,
      "el trabajador informa errores completos y permite configurar el intervalo")
check('class="card-title"' in SHOP and 'class="discount-badge"' in SHOP,
      "la tarjeta pública muestra título y porcentaje de descuento")
check('id="central-figma-card-v3"' not in SHOP,
      "no queda el bloque CSS que sobrescribía el marcado real de las tarjetas")
check('function preview(){const m=model();S.mountDetail($("preview"),{...m,links:{},fallback:""},0)' in CARDS,
      "la vista previa administrativa no abre enlaces externos")

check("catalog_expires_at IS NULL OR" not in API and "catalog_expires_at IS NULL OR" not in PUB,
      "la lectura respeta el aplazamiento de caducidad decidido por el trabajador")
check("p.current_price > 0" in API,
      "el radar y el catálogo administrativo excluyen productos sin precio real")
check("NULLIF(p.source_metadata->>'mongo_image_id', '')" in PUB and "COALESCE(pc.sale_price, p.current_price) > 0" in PUB,
      "el escaparate acepta imágenes Mongo persistidas y exige un precio numérico real")
check("p.is_active=TRUE AND p.is_blocked=FALSE AND COALESCE(pc.sale_price,p.current_price)>0" in API,
      "la ficha pública solo sirve publicaciones activas con precio verificable")

print("[PASS] Auditoría de contrato del catálogo completada.")
