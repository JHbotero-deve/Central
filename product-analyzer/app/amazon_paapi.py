"""
Cliente para Amazon Creators API.

IMPORTANTE (revisado 2026-09-10): la Product Advertising API 5.0 (PAAPI5),
que es la que usaba la versión anterior de este archivo con firma AWS
Signature V4, fue discontinuada por Amazon (deprecación anunciada para
abril/mayo de 2026 y ya no acepta cuentas nuevas). El reemplazo oficial es
la **Creators API**, que además es más simple: usa OAuth2 client_credentials
en lugar de firmar cada request a mano.

Requisitos actuales (según affiliate-program.amazon.com/creatorsapi/docs):
- Estar aprobado en el programa Amazon Associates.
- Tener al menos 10 ventas calificadas en los últimos 30 días para que se
  habilite el acceso a Creators API (antes eran 3 ventas en 180 días con
  PAAPI5 — el requisito subió).
- Registrarse específicamente para Creators API en Associates Central y
  generar un Client ID / Client Secret (ya NO son un Access Key / Secret
  Key estilo AWS).

Doc oficial: https://affiliate-program.amazon.com/creatorsapi/docs/en-us/introduction
Guía de migración: https://affiliate-program.amazon.com/creatorsapi/docs/en-us/migrating-to-creatorsapi-from-paapi

Antes de ir a producción con esto: confirmar el path exacto de SearchItems
contra la documentación oficial (los ejemplos publicados muestran
"/catalog/v1/getItems" para GetItems; "/catalog/v1/searchItems" sigue esa
misma convención pero no estaba listado con URL completa al momento de
escribir esto).
"""

import os
import time
import requests

# El endpoint de token depende de la región de tus credenciales (no del
# marketplace al que apuntás — para eso está AMAZON_MARKETPLACE / header
# x-marketplace). Ver "Regional Endpoints" en la doc de Creators API.
TOKEN_ENDPOINTS = {
    "NA": "https://api.amazon.com/auth/o2/token",       # US, CA, MX, BR
    "EU": "https://api.amazon.co.uk/auth/o2/token",     # UK, DE, FR, IT, ES, NL, BE, EG, IN, IE, PL, SA, SE, TR, AE
    "FE": "https://api.amazon.co.jp/auth/o2/token",     # JP, SG, AU
}

API_BASE = "https://creatorsapi.amazon"
SEARCH_URL = f"{API_BASE}/catalog/v1/searchItems"

# Cache simple en memoria del access_token (dura ~1h, ver expires_in).
_token_cache = {"access_token": None, "expires_at": 0.0}


def _get_access_token() -> str:
    now = time.time()
    if _token_cache["access_token"] and now < _token_cache["expires_at"] - 60:
        return _token_cache["access_token"]

    client_id = os.getenv("AMAZON_CLIENT_ID")
    client_secret = os.getenv("AMAZON_CLIENT_SECRET")
    region = os.getenv("AMAZON_REGION", "NA").upper()
    token_url = TOKEN_ENDPOINTS.get(region, TOKEN_ENDPOINTS["NA"])

    if not client_id or not client_secret:
        raise RuntimeError(
            "Faltan credenciales de Amazon Creators API (AMAZON_CLIENT_ID, "
            "AMAZON_CLIENT_SECRET). Revisa las variables de entorno."
        )

    resp = requests.post(
        token_url,
        headers={"Content-Type": "application/json"},
        json={
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
            "scope": "creatorsapi::default",
        },
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()

    _token_cache["access_token"] = data["access_token"]
    _token_cache["expires_at"] = now + data.get("expires_in", 3600)
    return _token_cache["access_token"]


def search_items(keywords: str, item_count: int = 10):
    partner_tag = os.getenv("AMAZON_PARTNER_TAG")
    marketplace = os.getenv("AMAZON_MARKETPLACE", "www.amazon.com")

    if not partner_tag:
        raise RuntimeError(
            "Falta AMAZON_PARTNER_TAG en las variables de entorno."
        )

    token = _get_access_token()

    payload = {
        "partnerTag": partner_tag,
        "keywords": keywords,
        "itemCount": min(max(item_count, 1), 10),  # la API acepta 1-10
        "marketplace": marketplace,
        "resources": [
            "itemInfo.title",
            "offersV2.listings.price",
            "images.primary.medium",
        ],
    }
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "x-marketplace": marketplace,
    }

    resp = requests.post(SEARCH_URL, headers=headers, json=payload, timeout=15)
    resp.raise_for_status()
    data = resp.json()

    products = []
    for item in data.get("searchResult", {}).get("items", []):
        title = item.get("itemInfo", {}).get("title", {}).get("displayValue")
        image = (
            item.get("images", {}).get("primary", {}).get("medium", {}).get("url")
        )
        listings = item.get("offersV2", {}).get("listings") or [{}]
        price_info = (listings[0].get("price") or {}).get("money", {})

        products.append({
            "external_id": item.get("asin"),
            "title": title,
            "image_url": image,
            "product_url": item.get("detailPageURL"),
            "price": price_info.get("amount"),
            "currency": price_info.get("currency", "USD"),
            # Creators API no devuelve rating/reviews en SearchItems (a
            # diferencia de PAAPI5); si se necesita, evaluar GetItems con
            # el resource correspondiente o completar manualmente.
            "rating": None,
            "reviews_count": None,
            "sales_estimate": None,
        })
    return products
