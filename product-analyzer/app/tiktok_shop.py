"""
Cliente real para TikTok Shop Open API (búsqueda de productos).

Requiere ser vendedor o partner aprobado en https://partner.tiktokshop.com
La API está pensada sobre todo para gestionar el catálogo propio; el acceso
a productos de otros vendedores es limitado y depende del scope aprobado.
"""

import os
import time
import hmac
import hashlib
import requests

BASE_URL = "https://open-api.tiktokglobalshop.com"


def _sign_request(app_secret: str, path: str, params: dict, body: str = "") -> str:
    """
    Firma HMAC-SHA256 según el esquema de TikTok Shop.

    OJO: el base string va envuelto con app_secret al principio Y al final
    (no solo como key del HMAC). Sin ese envoltorio, TikTok rechaza la
    firma con "sign invalid" aunque el resto de los datos sea correcto.
    Los parámetros 'sign' y 'access_token' se excluyen del cálculo (van
    en la request pero no entran en la firma).
    """
    filtered = {k: v for k, v in params.items(
    ) if k not in ("sign", "access_token")}
    sorted_params = "".join(f"{k}{v}" for k, v in sorted(filtered.items()))
    base_string = f"{app_secret}{path}{sorted_params}{body}{app_secret}"
    signed = hmac.new(
        app_secret.encode("utf-8"),
        base_string.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return signed


def search_products(keyword: str, page_size: int = 10):
    app_key = os.getenv("TIKTOK_API_KEY")
    app_secret = os.getenv("TIKTOK_API_SECRET")
    access_token = os.getenv("TIKTOK_ACCESS_TOKEN")
    # Desde la versión 202309 de la API, TikTok Shop pide "shop_cipher"
    # (no ya "shop_id") para identificar la tienda en la mayoría de los
    # endpoints. El cipher se obtiene junto con el id al consultar
    # /authorization/202309/shops (ver get_tiktok_token.py).
    shop_cipher = os.getenv("TIKTOK_SHOP_CIPHER")

    if not all([app_key, app_secret, access_token, shop_cipher]):
        raise RuntimeError(
            "Faltan credenciales de TikTok Shop (TIKTOK_API_KEY, "
            "TIKTOK_API_SECRET, TIKTOK_ACCESS_TOKEN, TIKTOK_SHOP_CIPHER)."
        )

    path = "/product/202309/products/search"
    timestamp = str(int(time.time()))

    params = {
        "app_key": app_key,
        "timestamp": timestamp,
        "shop_cipher": shop_cipher,
    }
    body = {"page_size": page_size, "search_keyword": keyword}
    body_json = requests.utils.json.dumps(body)

    params["sign"] = _sign_request(app_secret, path, params, body_json)
    params["access_token"] = access_token

    headers = {
        "content-type": "application/json",
        "x-tts-access-token": access_token,
    }

    resp = requests.post(BASE_URL + path, params=params, headers=headers,
                            data=body_json, timeout=15)
    resp.raise_for_status()
    data = resp.json()

    products = []
    for item in data.get("data", {}).get("products", []):
        products.append({
            "external_id": item.get("id"),
            "title": item.get("title"),
            "image_url": (item.get("images") or [{}])[0].get("url_list", [None])[0],
            "product_url": None,  # TikTok Shop no siempre expone URL pública directa
            "price": item.get("price", {}).get("sale_price"),
            "currency": item.get("price", {}).get("currency", "USD"),
            "rating": None,
            "reviews_count": None,
            "sales_estimate": item.get("sales_count"),
        })
    return products
