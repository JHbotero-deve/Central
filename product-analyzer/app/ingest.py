"""
Ingesta de productos de moda desde las distintas plataformas.

- Mercado Libre: usa su API pública de búsqueda (no requiere token para búsquedas simples).
- Amazon: requiere credenciales de Product Advertising API (PAAPI5). Se deja el stub
  listo; sin credenciales, devuelve datos de ejemplo para poder probar el pipeline.
- TikTok Shop: requiere ser partner aprobado de TikTok Shop API. Igual que Amazon,
  se deja el stub y datos de ejemplo.
"""

import os
import requests

import amazon_paapi
import tiktok_shop

MELI_SEARCH_URL = "https://api.mercadolibre.com/sites/MLA/search"


def fetch_mercadolibre(query: str, limit: int = 20):
    """Trae productos reales desde la API pública de Mercado Libre."""
    params = {"q": query, "limit": limit}
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    resp = requests.get(MELI_SEARCH_URL, params=params, headers=headers, timeout=10)
    resp.raise_for_status()
    data = resp.json()

    products = []
    for item in data.get("results", []):
        products.append({
            "external_id": item["id"],
            "title": item["title"],
            "image_url": item.get("thumbnail"),
            "product_url": item.get("permalink"),
            "price": item.get("price"),
            "currency": item.get("currency_id", "ARS"),
            "rating": None,  # la búsqueda pública no siempre trae rating
            "reviews_count": 0,
            "sales_estimate": item.get("sold_quantity"),
        })
    return products


def fetch_amazon(query: str):
    """
    Usa la API real de Amazon Creators API si están las credenciales completas
    (AMAZON_CLIENT_ID, AMAZON_CLIENT_SECRET, AMAZON_PARTNER_TAG). Si faltan,
    devuelve datos de ejemplo para poder probar el resto del pipeline.
    """
    if os.getenv("AMAZON_CLIENT_ID") and os.getenv("AMAZON_PARTNER_TAG"):
        try:
            return amazon_paapi.search_items(query)
        except Exception as e:
            print(f"[amazon] error con la API real, usando datos de ejemplo: {e}")

    return [{
        "external_id": "B0EXAMPLE1",
        "title": f"[EJEMPLO] {query} - producto Amazon",
        "image_url": None,
        "product_url": "https://amazon.com/dp/B0EXAMPLE1",
        "price": 24999.0,
        "currency": "ARS",
        "rating": 4.3,
        "reviews_count": 152,
        "sales_estimate": None,
    }]


def fetch_tiktok(query: str):
    """
    Usa la API real de TikTok Shop si están las credenciales completas
    (TIKTOK_API_KEY, TIKTOK_API_SECRET, TIKTOK_ACCESS_TOKEN, TIKTOK_SHOP_CIPHER).
    Si faltan, devuelve datos de ejemplo.
    """
    if os.getenv("TIKTOK_API_KEY") and os.getenv("TIKTOK_ACCESS_TOKEN") and os.getenv("TIKTOK_SHOP_CIPHER"):
        try:
            return tiktok_shop.search_products(query)
        except Exception as e:
            print(f"[tiktok] error con la API real, usando datos de ejemplo: {e}")

    return [{
        "external_id": "TT-EXAMPLE1",
        "title": f"[EJEMPLO] {query} - producto TikTok Shop",
        "image_url": None,
        "product_url": "https://shop.tiktok.com/example",
        "price": 21999.0,
        "currency": "ARS",
        "rating": 4.6,
        "reviews_count": 89,
        "sales_estimate": 340,
    }]
