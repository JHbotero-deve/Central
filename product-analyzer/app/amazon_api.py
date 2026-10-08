import os
import re
import time
from typing import Any

import requests

BASE_URL = "https://creatorsapi.amazon"
MARKETPLACE = os.getenv("AMAZON_MARKETPLACE", "www.amazon.com")
CREDENTIAL_ID = os.getenv("AMAZON_CREDENTIAL_ID", "").strip()
CREDENTIAL_SECRET = os.getenv("AMAZON_CREDENTIAL_SECRET", "").strip()
PARTNER_TAG = os.getenv("AMAZON_PARTNER_TAG", "").strip()
CREDENTIAL_VERSION = os.getenv("AMAZON_CREDENTIAL_VERSION", "3.1").strip()

_TOKEN: str | None = None
_TOKEN_EXPIRES_AT = 0.0
_TOKEN_VERSION = ""


def _access_token() -> str:
    global _TOKEN, _TOKEN_EXPIRES_AT, _TOKEN_VERSION

    if _TOKEN and time.time() < _TOKEN_EXPIRES_AT - 120:
        return _TOKEN

    if not CREDENTIAL_ID or not CREDENTIAL_SECRET or not PARTNER_TAG:
        raise RuntimeError("Faltan AMAZON_CREDENTIAL_ID, AMAZON_CREDENTIAL_SECRET o AMAZON_PARTNER_TAG")

    versions = ["3.1","3.2","3.3","2.1","2.2","2.3"]
    candidates = ([CREDENTIAL_VERSION] + [v for v in versions if v != CREDENTIAL_VERSION]) if CREDENTIAL_VERSION in versions else versions
    configs = {
        "3.1": ("https://api.amazon.com/auth/o2/token", "creatorsapi::default", False),
        "3.2": ("https://api.amazon.co.uk/auth/o2/token", "creatorsapi::default", False),
        "3.3": ("https://api.amazon.co.jp/auth/o2/token", "creatorsapi::default", False),
        "2.1": ("https://creatorsapi.auth.us-east-1.amazoncognito.com/oauth2/token", "creatorsapi/default", True),
        "2.2": ("https://creatorsapi.auth.eu-south-2.amazoncognito.com/oauth2/token", "creatorsapi/default", True),
        "2.3": ("https://creatorsapi.auth.us-west-2.amazoncognito.com/oauth2/token", "creatorsapi/default", True),
    }
    errors = []
    for version in candidates:
        endpoint, scope, cognito = configs[version]
        try:
            if cognito:
                response = requests.post(endpoint, headers={"Content-Type":"application/x-www-form-urlencoded"}, data={"grant_type":"client_credentials","client_id":CREDENTIAL_ID,"client_secret":CREDENTIAL_SECRET,"scope":scope}, timeout=20)
            else:
                response = requests.post(endpoint, headers={"Content-Type":"application/json"}, json={"grant_type":"client_credentials","client_id":CREDENTIAL_ID,"client_secret":CREDENTIAL_SECRET,"scope":scope}, timeout=20)
            if response.ok:
                data = response.json()
                token = data.get("access_token")
                if token:
                    _TOKEN = token
                    _TOKEN_VERSION = version
                    _TOKEN_EXPIRES_AT = time.time() + int(data.get("expires_in",3600))
                    print("[amazon] Creators API autenticado con credencial " + version + ".")
                    return token
            try:
                detail = response.json()
                detail = detail.get("error_description") or detail.get("error") or str(detail)
            except ValueError:
                detail = response.text[:300]
            errors.append(version + ": HTTP " + str(response.status_code) + ": " + str(detail))
        except requests.RequestException as exc:
            errors.append(version + ": " + type(exc).__name__ + ": " + str(exc))
    raise RuntimeError("Amazon OAuth rechazó las credenciales; " + " | ".join(errors))



def _request(operation: str, payload: dict[str, Any]) -> dict[str, Any]:
    payload = dict(payload)
    payload["marketplace"] = MARKETPLACE
    payload["partnerTag"] = PARTNER_TAG

    def do_request() -> requests.Response:
        return requests.post(
            f"{BASE_URL}/catalog/v1/{operation}",
            headers={
                "Authorization": (
                    f"Bearer {_access_token()}"
                    + (f", Version {_TOKEN_VERSION}" if _TOKEN_VERSION.startswith("2.") else "")
                ),
                "Content-Type": "application/json",
                "x-marketplace": MARKETPLACE,
            },
            json=payload,
            timeout=30,
        )

    response = do_request()

    if response.status_code == 401:
        global _TOKEN, _TOKEN_EXPIRES_AT, _TOKEN_VERSION
        _TOKEN = None
        _TOKEN_EXPIRES_AT = 0
        _TOKEN_VERSION = ""
        response = do_request()

    response.raise_for_status()

    data = response.json()

    if data.get("errors"):
        raise RuntimeError(str(data["errors"]))

    return data


def _first_image(item: dict[str, Any]) -> str | None:
    images = item.get("images") or {}
    primary = images.get("primary") or {}

    for key in ("large", "medium", "small"):
        node = primary.get(key) or {}
        url = node.get("url")

        if url:
            return str(url)

    return None


def _title(item: dict[str, Any]) -> str | None:
    title = (
        ((item.get("itemInfo") or {}).get("title") or {}).get("displayValue")
    )

    return str(title).strip() if title else None


def _offer(item: dict[str, Any]) -> tuple[float | None, str | None]:
    listings = (
        ((item.get("offersV2") or {}).get("listings") or [])
    )

    if not listings:
        return None, None

    price = listings[0].get("price") or {}
    amount = price.get("amount")
    currency = price.get("currency")

    try:
        return (
            (float(amount), str(currency).upper())
            if amount is not None
            else (None, None)
        )
    except (TypeError, ValueError):
        return None, None


def _amazon_image_from_html(url: str) -> str | None:
    """
    Fallback para páginas Amazon cuando Creators API no está disponible.

    Busca primero og:image y luego imágenes conocidas dentro del HTML.
    No genera imágenes ni inventa URLs.
    """
    try:
        response = requests.get(
            url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/140.0 Safari/537.36"
                ),
                "Accept-Language": "en-US,en;q=0.9",
            },
            timeout=20,
            allow_redirects=True,
        )

        if not response.ok:
            return None

        html = response.text

        patterns = [
            r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)',
            r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']',
            r'<meta[^>]+name=["\']twitter:image["\'][^>]+content=["\']([^"\']+)',
            r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+name=["\']twitter:image["\']',
        ]

        for pattern in patterns:
            match = re.search(pattern, html, re.IGNORECASE)

            if match:
                image = match.group(1).strip()

                if image.startswith("https://"):
                    return image

        return None

    except requests.RequestException as exc:
        print(f"[amazon] fallback imagen error: {exc}")
        return None


def _search_amazon_html(keywords: str, limit: int = 10) -> list[dict[str, Any]]:
    """Fallback real: obtiene candidatos directamente de resultados públicos de Amazon."""
    try:
        response = requests.get(
            "https://www.amazon.com/s",
            params={"k": keywords},
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/140.0 Safari/537.36"
                ),
                "Accept-Language": "en-US,en;q=0.9",
            },
            timeout=25,
            allow_redirects=True,
        )
        response.raise_for_status()
        html = response.text
        asins = re.findall(r"data-asin=[\"']([A-Z0-9]{10})[\"']", html, re.IGNORECASE)
        results = []
        seen = set()

        for raw_asin in asins:
            asin = raw_asin.upper()
            if asin in seen:
                continue
            marker = re.search(
                r"data-asin=[\"']" + re.escape(asin) + r"[\"']",
                html,
                re.IGNORECASE,
            )
            if not marker:
                continue
            seen.add(asin)
            start = marker.start()
            next_marker = re.search(
                r"data-asin=[\"'][A-Z0-9]{10}[\"']",
                html[marker.end():],
                re.IGNORECASE,
            )
            end = marker.end() + next_marker.start() if next_marker else min(len(html), start + 60000)
            chunk = html[start:end]

            title_match = re.search(
                r"<span[^>]+class=[\"'][^\"']*a-text-normal[^\"']*[\"'][^>]*>(.*?)</span>",
                chunk, re.IGNORECASE | re.DOTALL)
            title = re.sub(r"<[^>]+>", " ", title_match.group(1)) if title_match else ""
            title = re.sub(r"\s+", " ", title).strip()

            image = None
            dynamic = re.search(r"data-a-dynamic-image=[\"']([^\"']+)[\"']", chunk, re.IGNORECASE)
            if dynamic:
                raw = dynamic.group(1).replace("&quot;", '"')
                image_match = re.search(r'"(https?://[^"]+)"', raw)
                image = image_match.group(1) if image_match else None
            if not image:
                image_match = re.search(r"<img[^>]+src=[\"'](https?://[^\"']+)[\"']", chunk, re.IGNORECASE)
                image = image_match.group(1) if image_match else None

            price_match = re.search(
                r"<span[^>]+class=[\"'][^\"']*a-price-whole[^\"']*[\"'][^>]*>([0-9,]+)</span>"
                r"(?:.*?<span[^>]+class=[\"'][^\"']*a-price-fraction[^\"']*[\"'][^>]*>([0-9]+)</span>)?",
                chunk, re.IGNORECASE | re.DOTALL)
            if not price_match:
                continue

            try:
                amount = float(
                    price_match.group(1).replace(",", "")
                    + "."
                    + (price_match.group(2) or "00")
                )
            except ValueError:
                continue

            if not title or not image or amount <= 0:
                continue

            results.append({
                "asin": asin,
                "detailPageURL": f"https://www.amazon.com/dp/{asin}",
                "itemInfo": {"title": {"displayValue": title[:500]}},
                "offersV2": {"listings": [{"price": {"amount": amount, "currency": "USD"}}]},
                "images": {"primary": {"large": {"url": image}}},
            })
            if len(results) >= min(max(limit, 1), 20):
                break

        print(f"[amazon] búsqueda HTML real '{keywords}': {len(results)} productos")
        return results
    except requests.RequestException as exc:
        print(f"[amazon] fallback búsqueda HTML error: {exc}")
        return []


def _search_amazon_web(keywords: str, limit: int = 10) -> list[dict[str, Any]]:
    """Fallback real usando el índice web de Bing cuando Amazon bloquea HTML directo."""
    try:
        response = requests.get(
            "https://www.bing.com/search",
            params={"q": f'site:amazon.com/dp "{keywords}"', "count": min(max(limit * 2, 10), 30)},
            headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/140 Safari/537.36", "Accept-Language": "en-US,en;q=0.9"},
            timeout=25,
        )
        response.raise_for_status()
        page = response.text
        products = []
        seen = set()
        pattern = re.compile(r"href=[\"'](https?://(?:www\.|us\.)?amazon\.com/(?:[^\"']*?/)?(?:dp|gp/product)/([A-Z0-9]{10})(?:[/?][^\"']*)?)[\"']", re.I)
        for match in pattern.finditer(page):
            url, asin = match.group(1), match.group(2).upper()
            if asin in seen:
                continue
            chunk = page[max(0, match.start() - 2500):min(len(page), match.end() + 5000)]
            title_match = re.search(r"<h2[^>]*>(.*?)</h2>|<h3[^>]*>(.*?)</h3>|<a[^>]*>(.*?)</a>", chunk, re.I | re.S)
            title = ""
            if title_match:
                title = next((x for x in title_match.groups() if x), "")
            title = re.sub(r"<[^>]+>", " ", title)
            title = re.sub(r"\s+", " ", title).strip()
            price_match = re.search(r"\$\s*([0-9][0-9,]*(?:\.[0-9]{1,2})?)", chunk)
            if not price_match or not title or title.lower() in {"amazon.com", "amazon"}:
                continue
            try:
                amount = float(price_match.group(1).replace(",", ""))
            except ValueError:
                continue
            if amount <= 0:
                continue
            seen.add(asin)
            products.append({
                "asin": asin,
                "detailPageURL": url,
                "itemInfo": {"title": {"displayValue": title[:500]}},
                "offersV2": {"listings": [{"price": {"amount": amount, "currency": "USD"}}]},
                "images": _fallback_images(url),
            })
            if len(products) >= min(max(limit, 1), 20):
                break
        print(f"[amazon] fallback Bing real '{keywords}': {len(products)} productos")
        return products
    except (requests.RequestException, ValueError) as exc:
        print(f"[amazon] fallback Bing error: {exc}")
        return []


def _fallback_images(url: str) -> dict[str, Any]:
    """Imagen real tomada de la pagina del producto; sin imagen si no se obtiene (nunca una URL inventada)."""
    try:
        img = _amazon_image_from_html(str(url))
    except Exception:
        img = None
    return {"primary": {"large": {"url": img}}} if img else {}


def search_products(keywords: str, limit: int = 10) -> list[dict[str, Any]]:
    try:
        data = _request(
            "searchItems",
            {
                "keywords": keywords,
                "searchIndex": "All",
                "itemCount": min(max(limit, 1), 10),
                "sortBy": "Relevance",
                "resources": [
                    "images.primary.large",
                    "images.primary.medium",
                    "images.primary.small",
                    "itemInfo.title",
                    "offersV2.listings.price",
                ],
            },
        )
        items = ((data.get("searchResult") or {}).get("items") or [])
        if items:
            return items
    except Exception as exc:
        print(f"[amazon] Creators API no disponible para '{keywords}': {exc}")

    html_results = _search_amazon_html(keywords, limit)
    if html_results:
        return html_results
    return _search_amazon_web(keywords, limit)


def _map_item(
    item: dict[str, Any],
    category: str,
    allow_missing_image: bool = False,
) -> dict[str, Any] | None:

    asin = str(item.get("asin") or "").strip().upper()
    title = _title(item)
    image = _first_image(item)
    price, currency = _offer(item)
    url = item.get("detailPageURL")

    if not asin or not title or price is None or not url:
        return None

    if not image and not allow_missing_image:
        return None

    return {
        "platform": "amazon",
        "external_id": asin,
        "title": title[:500],
        "image_url": image,
        "gallery_urls": [image] if image else [],
        "product_url": str(url),
        "price": price,
        "currency": currency or "USD",
        "rating": None,
        "reviews_count": 0,
        "sales_estimate": None,
        "source_metadata": {
            "import_method": "creators_api",
            "metadata_source": "amazon_creators_api",
            "marketplace": MARKETPLACE,
            "keywords": category,
        },
    }


def _map_fallback_item(
    item: dict[str, Any],
    category: str,
) -> dict[str, Any] | None:

    asin = str(item.get("asin") or "").strip().upper()
    title = _title(item)
    price, currency = _offer(item)
    url = item.get("detailPageURL")

    if not asin or not title or price is None or not url:
        return None

    image = _amazon_image_from_html(str(url))

    return {
        "platform": "amazon",
        "external_id": asin,
        "title": title[:500],
        "image_url": image,
        "gallery_urls": [image] if image else [],
        "product_url": str(url),
        "price": price,
        "currency": currency or "USD",
        "rating": None,
        "reviews_count": 0,
        "sales_estimate": None,
        "source_metadata": {
            "import_method": "creators_api_fallback",
            "metadata_source": "amazon_product_page",
            "marketplace": MARKETPLACE,
            "keywords": category,
            "image_source": "og:image" if image else None,
        },
    }


def fetch_amazon_seed_products(existing_ids: set[str], limit: int = 10) -> list[tuple[str, dict[str, Any]]]:
    """Seed real Amazon products from known ASIN links when search APIs are unavailable."""
    seeds = [
        ("Electronics", "B0CN5HYDHZ"),
        ("Electronics", "B0DM83L2R2"),
        ("Computers", "B0DZMLL649"),
        ("Computers", "B0D2NHPXK7"),
        ("Computers", "B0DSJVKHZG"),
        ("Computers", "B0D7JL9RKL"),
        ("Computers", "B0BYLNF9XF"),
        ("Computers", "B0CQNBG45Z"),
        ("Electronics", "B0C6RC1DVL"),
        ("Electronics", "B08CZCXV9M"),
    ]
    results = []
    seen = set(existing_ids)
    for category, asin in seeds:
        if asin in seen or len(results) >= limit:
            continue
        url = f"https://www.amazon.com/dp/{asin}"
        try:
            response = requests.get(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/140.0 Safari/537.36", "Accept-Language": "en-US,en;q=0.9"}, timeout=20, allow_redirects=True)
            if not response.ok:
                continue
            html = response.text
            title_match = re.search(r"""<meta[^>]+property=["']og:title["'][^>]+content=["']([^"']+)""", html, re.I)
            title = title_match.group(1).strip() if title_match else ""
            if not title:
                title_match = re.search(r"""<span[^>]+id=["']productTitle["'][^>]*>(.*?)</span>""", html, re.I | re.S)
                title = re.sub(r"<[^>]+>", " ", title_match.group(1)).strip() if title_match else ""
            image = _amazon_image_from_html(url)
            price_match = re.search(r"""<span[^>]+class=["'](?:[^"']*a-price-whole)[^"']*["'][^>]*>([0-9,]+)</span>.*?<span[^>]+class=["'](?:[^"']*a-price-fraction)[^"']*["'][^>]*>([0-9]+)</span>""", html, re.I | re.S)
            if not price_match:
                price_match = re.search(r"""\$\s*([0-9][0-9,]*(?:\.[0-9]{1,2})?)""", html)
                amount = float(price_match.group(1).replace(",", "")) if price_match else None
            else:
                amount = float(price_match.group(1).replace(",", "") + "." + price_match.group(2))
            if not title or not image or not amount or amount <= 0:
                continue
            product = {"platform":"amazon","external_id":asin,"title":title[:500],"image_url":image,"gallery_urls":[image],"product_url":url,"price":amount,"currency":"USD","rating":None,"reviews_count":0,"sales_estimate":None,"source_metadata":{"import_method":"amazon_seed","metadata_source":"amazon_product_page","marketplace":MARKETPLACE,"asin":asin}}
            results.append((category, product)); seen.add(asin)
        except (requests.RequestException, ValueError) as exc:
            print(f"[amazon] seed {asin} error: {exc}")
    print(f"[amazon] seed real: {len(results)} productos válidos")
    return results


def fetch_amazon_products(
    existing_ids: set[str],
    limit: int = 15,
) -> list[tuple[str, dict[str, Any]]]:

    searches = [
        ("Electronics", "wireless headphones"),
        ("Electronics", "bluetooth earbuds"),
        ("Electronics", "smart watch"),
        ("Electronics", "power bank"),
        ("Electronics", "USB C charger"),
        ("Computers", "mechanical keyboard"),
        ("Computers", "gaming mouse"),
        ("Computers", "webcam"),
        ("Computers", "portable SSD"),
        ("Computers", "4k monitor"),
        ("HomeAndKitchen", "home gadgets"),
        ("HomeAndKitchen", "security camera wifi"),
        ("SportsAndOutdoors", "fitness accessories"),
        ("VideoGames", "gaming accessories"),
        ("VideoGames", "game controller"),
        ("Shoes", "mens sneakers"),
        ("Shoes", "womens sneakers"),
    ]

    results: list[tuple[str, dict[str, Any]]] = []
    seen = set(existing_ids)

    for category, keywords in searches:
        try:
            items = search_products(keywords, 10)
            added = 0

            for item in items:
                product = _map_item(item, category)

                if not product:
                    product = _map_fallback_item(item, category)

                if not product:
                    continue

                if product["external_id"] in seen:
                    continue

                seen.add(product["external_id"])
                results.append((category, product))
                added += 1

                if len(results) >= limit:
                    return results

            print(
                f"[amazon] {keywords}: "
                f"{added} productos nuevos válidos"
            )

        except Exception as exc:
            print(
                f"[amazon] error buscando '{keywords}': {exc}"
            )

    return results
