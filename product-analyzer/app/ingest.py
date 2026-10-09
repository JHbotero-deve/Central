from meli_oauth import get_meli_tokens, save_meli_tokens
import os
import json
import re
from urllib.parse import quote_plus
import requests

MELI_SEARCH = "https://api.mercadolibre.com/sites/MCO/search"
MELI_ITEM = "https://api.mercadolibre.com/items/{id}"
MELI_PRICES = "https://api.mercadolibre.com/items/{id}/prices"
MELI_SALE_PRICE = "https://api.mercadolibre.com/items/{id}/sale_price"
MELI_OAUTH = "https://api.mercadolibre.com/oauth/token"
MELI_PRODUCTS_SEARCH = "https://api.mercadolibre.com/products/search"
MELI_PRODUCT = "https://api.mercadolibre.com/products/{id}"


def _headers(include_auth=True):
    headers = {
        "User-Agent": "CentralProductAnalyzer/2.2",
        "Accept": "application/json",
    }
    token, _ = get_meli_tokens()
    token = token or (os.getenv("MELI_ACCESS_TOKEN", "").strip() or os.getenv("MERCADOLIBRE_ACCESS_TOKEN", "").strip())
    if include_auth and token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _refresh_access_token():
    _, refresh_token = get_meli_tokens()
    client_id = os.getenv("MELI_CLIENT_ID", "").strip()
    client_secret = os.getenv("MELI_CLIENT_SECRET", "").strip()
    if not (refresh_token and client_id and client_secret):
        return None
    response = requests.post(MELI_OAUTH, data={
        "grant_type": "refresh_token",
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": refresh_token,
    }, timeout=20)
    if not response.ok:
        print(f"[Mercado Libre] renovación de token: HTTP {response.status_code}")
        return None
    payload = response.json()
    token = str(payload.get("access_token") or "").strip()
    new_refresh = str(payload.get("refresh_token") or "").strip()
    if token and new_refresh:
        save_meli_tokens(token, new_refresh, int(payload.get("expires_in") or 0))
        print("[Mercado Libre] access token renovado.")
    return token or None


def _get(url, params=None, include_auth=True, retry_auth=True):
    response = requests.get(
        url,
        params=params,
        headers=_headers(include_auth),
        timeout=20,
    )
    if response.status_code == 401 and include_auth and retry_auth:
        refreshed = _refresh_access_token()
        if refreshed:
            response = requests.get(
                url,
                params=params,
                headers={
                    "User-Agent": "CentralProductAnalyzer/2.3",
                    "Accept": "application/json",
                    "Authorization": f"Bearer {refreshed}",
                },
                timeout=20,
            )
    if response.status_code == 401:
        raise RuntimeError("Mercado Libre rechazó el token de acceso")
    if response.status_code == 403:
        try:
            payload = response.json()
            reason = payload.get("message") or payload.get("error") or payload.get("code")
        except ValueError:
            reason = response.text[:180].strip()
        suffix = f": {reason}" if reason else ""
        raise RuntimeError(f"Mercado Libre rechazó la consulta (403){suffix}")
    response.raise_for_status()
    return response.json()


def _details(item_id):
    try:
        return _get(MELI_ITEM.format(id=item_id))
    except (requests.RequestException, RuntimeError) as exc:
        print(f"[Mercado Libre] detalle {item_id}: {exc}")
        return {}


def _prices(item_id):
    try:
        return _get(MELI_PRICES.format(id=item_id)).get("prices") or []
    except (requests.RequestException, RuntimeError) as exc:
        print(f"[Mercado Libre] prices {item_id}: {exc}")
        return []


def _sale_price(item_id):
    try:
        return _get(
            MELI_SALE_PRICE.format(id=item_id),
            {"context": "channel_marketplace"},
        )
    except (requests.RequestException, RuntimeError) as exc:
        print(f"[Mercado Libre] sale_price {item_id}: {exc}")
        return {}


def _public_search(query, limit=20):
    """Obtiene publicaciones reales de Mercado Libre mediante su página pública."""
    import unicodedata
    from html import unescape
    from urllib.parse import unquote

    slug = unicodedata.normalize("NFKD", query).encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", slug).strip("-").lower()
    listing_url = f"https://listado.mercadolibre.com.co/{slug}"
    reader_url = "https://r.jina.ai/" + listing_url

    try:
        response = requests.get(
            reader_url,
            headers={"User-Agent": "Mozilla/5.0", "Accept": "text/plain"},
            timeout=30,
        )
        response.raise_for_status()
        text = response.text
    except requests.RequestException as exc:
        print(f"[Mercado Libre] lector web no disponible '{query}': {exc}")
        return {"results": [], "_source": "public_web"}

    products, seen = [], set()
    # Markdown de Jina conserva los enlaces e imágenes de las tarjetas.
    link_re = re.compile(r"\[([^\]]{8,500})\]\((https?://[^)]+mercadolibre\.com\.co/[^)]+)\)", re.I)
    image_re = re.compile(r"!\[[^\]]*\]\((https?://[^)]+)\)", re.I)
    matches = list(link_re.finditer(text))

    for idx, match in enumerate(matches):
        title = unescape(re.sub(r"\s+", " ", match.group(1))).strip()
        permalink = unquote(match.group(2))
        if "/listado/" in permalink or "/categorias/" in permalink:
            continue
        if not title or permalink in seen:
            continue

        window = text[match.end(): matches[idx + 1].start() if idx + 1 < len(matches) else min(len(text), match.end() + 1800)]
        price_match = re.search(r"\$\s*([0-9][0-9.]{2,})", window)
        if not price_match:
            continue
        amount = float(price_match.group(1).replace(".", ""))
        if amount <= 0:
            continue

        image_match = image_re.search(text[max(0, match.start()-1200):match.end()+1200])
        image = image_match.group(1) if image_match else ""

        # Si la tarjeta no trae imagen, consultamos la página del producto a través del lector.
        if not image:
            try:
                detail = requests.get(
                    "https://r.jina.ai/" + permalink,
                    headers={"User-Agent": "Mozilla/5.0", "Accept": "text/plain"},
                    timeout=20,
                )
                if detail.ok:
                    dm = image_re.search(detail.text)
                    if dm:
                        image = dm.group(1)
            except requests.RequestException:
                pass

        item_match = re.search(r"(MCO[-_]\d{6,})", permalink, re.I)
        item_id = item_match.group(1).replace("_", "-").upper() if item_match else ""
        if not item_id:
            # Las URLs de publicación pueden no incluir el ID; se genera una clave estable.
            import hashlib
            item_id = "WEB-" + hashlib.sha1(permalink.encode("utf-8")).hexdigest()[:16].upper()

        seen.add(permalink)
        products.append({
            "id": item_id,
            "title": title[:500],
            "thumbnail": image,
            "permalink": permalink,
            "price": amount,
            "currency_id": "COP",
        })
        if len(products) >= min(max(limit, 1), 20):
            break

    print(f"[Mercado Libre] página pública real '{query}': {len(products)} productos")
    return {"results": products, "_source": "public_web"}



def _catalog_search(query, limit=20):
    """Mercado Libre catalog search: alternativa vigente al /sites/MCO/search bloqueado."""
    try:
        data = _get(MELI_PRODUCTS_SEARCH, {
            "status": "active", "site_id": "MCO", "q": query, "limit": min(limit, 20)
        }, include_auth=True)
    except (RuntimeError, requests.RequestException) as exc:
        print(f"[Mercado Libre] catalog search '{query}' no disponible: {exc}")
        return []
    products = []
    for result in data.get("results", []):
        product_id = result.get("id")
        if not product_id:
            continue
        try:
            detail = _get(MELI_PRODUCT.format(id=product_id), include_auth=True)
        except (RuntimeError, requests.RequestException):
            continue
        winner = detail.get("buy_box_winner") or {}
        price = winner.get("price")
        if not price:
            continue
        pictures = detail.get("pictures") or []
        image = (pictures[0].get("url") if pictures else "") or ""
        item_id = winner.get("item_id") or product_id
        products.append({
            "external_id": item_id,
            "title": detail.get("name") or result.get("name") or query,
            "image_url": image,
            "product_url": winner.get("permalink") or detail.get("permalink") or "",
            "price": float(price),
            "currency": winner.get("currency_id") or "COP",
            "rating": None,
            "reviews_count": 0,
            "sales_estimate": winner.get("sold_quantity") or detail.get("sold_quantity"),
            "seller": {"external_id": str(winner.get("seller_id") or "") or None, "name": None, "reputation": None},
            "source_metadata": {"catalog_product_id": product_id, "catalog": True, "buy_box_winner": winner},
        })
    print(f"[Mercado Libre] catalogo real '{query}': {len(products)} productos")
    return products


def fetch_mercadolibre(query, limit=20):
    # Primero intentamos la API autenticada. La búsqueda pública puede devolver
    # 403 desde Railway aunque el endpoint siga funcionando con OAuth.
    try:
        data = _get(MELI_SEARCH, {"q": query, "limit": min(limit, 50)}, include_auth=True)
        print(f"[Mercado Libre] API autenticada OK '{query}': {len(data.get('results') or [])} resultados")
    except (RuntimeError, requests.RequestException) as exc:
        if isinstance(exc, RuntimeError) and "403" not in str(exc):
            raise
        print(f"[Mercado Libre] API autenticada bloqueada para '{query}': {exc}")
        catalog_products = []
        try:
            data = _get(
                MELI_SEARCH,
                {"q": query, "limit": min(limit, 50)},
                include_auth=False,
                retry_auth=False,
            )
            print(f"[Mercado Libre] API pública OK '{query}': {len(data.get('results') or [])} resultados")
        except (RuntimeError, requests.RequestException) as public_exc:
            print(f"[Mercado Libre] API pública no disponible '{query}': {public_exc}")
            catalog_products = _catalog_search(query, limit)
        if catalog_products:
            print(f"[Mercado Libre] usando catálogo autenticado '{query}': {len(catalog_products)} productos")
            return catalog_products
        print(f"[Mercado Libre] catálogo sin resultados; usando búsqueda web real '{query}'")
        data = _public_search(query, limit)
    products = []

    public_web = data.get("_source") == "public_web"
    for item in data.get("results", []):
        item_id = item.get("id")
        title = item.get("title")
        if not item_id or not title:
            continue

        if public_web:
            detail, prices, sale = {}, [], {}
        else:
            detail = _details(item_id)
            prices = _prices(item_id)
            sale = _sale_price(item_id)

        price = (
            sale.get("amount")
            or detail.get("price")
            or item.get("price")
        )
        currency = (
            sale.get("currency_id")
            or detail.get("currency_id")
            or item.get("currency_id")
            or "COP"
        )

        if price in (None, 0) and prices:
            current = sorted(
                prices,
                key=lambda value: value.get("last_updated") or "",
                reverse=True,
            )[0]
            price = current.get("amount")
            currency = current.get("currency_id") or currency

        if price in (None, 0):
            continue

        seller_id = detail.get("seller_id") or (item.get("seller") or {}).get("id")
        metadata = {
            "search_result": item,
            "item": detail,
            "prices": prices,
            "sale_price": sale,
            "site_id": "MCO",
            "category_id": detail.get("category_id"),
            "condition": detail.get("condition"),
            "buying_mode": detail.get("buying_mode"),
            "listing_type_id": detail.get("listing_type_id"),
            "status": detail.get("status"),
            "available_quantity": detail.get("available_quantity"),
            "sold_quantity": detail.get("sold_quantity"),
            "shipping": detail.get("shipping") or {},
            "attributes": detail.get("attributes") or [],
            "variations": detail.get("variations") or [],
            "tags": detail.get("tags") or [],
        }

        products.append({
            "external_id": item_id,
            "title": title,
            "image_url": (
                detail.get("thumbnail")
                or item.get("thumbnail")
                or ""
            ).replace("-I.", "-O."),
            "product_url": detail.get("permalink") or item.get("permalink"),
            "price": float(price),
            "currency": currency,
            "rating": None,
            "reviews_count": 0,
            "sales_estimate": detail.get("sold_quantity") or item.get("sold_quantity"),
            "seller": {
                "external_id": str(seller_id) if seller_id else None,
                "name": None,
                "reputation": None,
            },
            "source_metadata": metadata,
        })

    print(f"[Mercado Libre MCO] {query}: {len(products)} productos reales completos")
    return products


def fetch_amazon(query, limit=10):
    return amazon_search_items(query, min(limit, 10))


def fetch_tiktok(query, limit=20):
    return tiktok_search_products(query, min(limit, 100))
