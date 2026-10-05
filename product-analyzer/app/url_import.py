import html
import ipaddress
import json
import re
import socket
from urllib.parse import urlparse

import requests

AMAZON_HOST_RE = re.compile(r"(^|\\.)amazon\\.[a-z.]+$", re.I)
MELI_HOST_RE = re.compile(r"(^|\\.)(mercadolibre|mercadolivre)\\.[a-z.]+$", re.I)
TIKTOK_HOST_RE = re.compile(r"(^|\\.)tiktok(?:shop)?\\.com$", re.I)
ASIN_RE = re.compile(r"(?:/dp/|/gp/product/)([A-Z0-9]{10})(?:[/?]|$)", re.I)
BLOCKED_HOSTS = {"localhost", "metadata.google.internal", "host.docker.internal"}


def _public_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ValueError("La URL debe comenzar con http:// o https://.")
    host = parsed.hostname.lower().rstrip(".")
    if host in BLOCKED_HOSTS or host.endswith(".local"):
        raise ValueError("La URL no apunta a un origen público permitido.")
    try:
        addresses = socket.getaddrinfo(host, parsed.port or (443 if parsed.scheme == "https" else 80), type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise ValueError("No fue posible resolver el dominio de la URL.") from exc
    for address in addresses:
        ip = ipaddress.ip_address(address[4][0])
        if not ip.is_global:
            raise ValueError("La URL no apunta a un origen público permitido.")


def detect_platform(url: str) -> str:
    host = (urlparse(url).hostname or "").lower()
    if AMAZON_HOST_RE.search(host):
        return "amazon"
    if MELI_HOST_RE.search(host):
        return "mercadolibre"
    if TIKTOK_HOST_RE.search(host):
        return "tiktok"
    raise ValueError("La URL debe pertenecer a Amazon, Mercado Libre o TikTok Shop.")


def _asin(url: str) -> str | None:
    match = ASIN_RE.search(urlparse(url).path)
    return match.group(1).upper() if match else None


def _parse_price(content: str) -> tuple[float | None, str | None]:
    content = html.unescape(content)
    marker = re.search(r'id=["\\']corePriceDisplay_desktop_feature_div["\\']', content, re.I)
    if marker:
        block = content[marker.start():marker.start() + 30000]
        price_match = re.search(
            r'<span[^>]+class=["\\'][^"\\']*a-price[^"\\']*["\\'][^>]*>.*?'
            r'<span[^>]+class=["\\'][^"\\']*a-price-symbol[^"\\']*["\\'][^>]*>\\s*([^<]+?)\\s*</span>.*?'
            r'<span[^>]+class=["\\'][^"\\']*a-price-whole[^"\\']*["\\'][^>]*>\\s*([0-9][0-9,]*)\\s*</span>.*?'
            r'<span[^>]+class=["\\'][^"\\']*a-price-fraction[^"\\']*["\\'][^>]*>\\s*([0-9]{1,2})\\s*</span>',
            block,
            re.I | re.S,
        )
        if price_match:
            symbol, whole, fraction = price_match.groups()
            currency = {"$": "USD", "€": "EUR", "£": "GBP"}.get(symbol.strip())
            if currency:
                try:
                    value = float(f"{whole.replace(',', '')}.{fraction}")
                    if value > 0:
                        return value, currency
                except ValueError:
                    pass
    for element_id in ("priceblock_ourprice", "priceblock_dealprice", "priceblock_saleprice"):
        match = re.search(rf'id=["\\']{element_id}["\\'][^>]*>\\s*([^<]+)', content, re.I | re.S)
        if not match:
            continue
        text = html.unescape(match.group(1)).strip()
        symbol = "$" if "$" in text else "€" if "€" in text else "£" if "£" in text else None
        currency = {"$": "USD", "€": "EUR", "£": "GBP"}.get(symbol)
        number = re.search(r"([0-9][0-9,]*(?:\\.[0-9]{1,2})?)", text) if currency else None
        if number:
            value = float(number.group(1).replace(",", ""))
            if value > 0:
                return value, currency
    return None, None


def _jsonld(content: str) -> list[dict]:
    nodes = []
    for match in re.finditer(r'<script[^>]+type=["\\']application/ld\\+json["\\'][^>]*>(.*?)</script>', content, re.I | re.S):
        try:
            data = json.loads(html.unescape(match.group(1)))
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
        values = data if isinstance(data, list) else [data]
        for value in values:
            if isinstance(value, dict):
                nodes.append(value)
                graph = value.get("@graph")
                if isinstance(graph, list):
                    nodes.extend(node for node in graph if isinstance(node, dict))
    return nodes


def _gallery_from_content(content: str) -> list[str]:
    urls = []
    for node in _jsonld(content):
        images = node.get("image")
        if isinstance(images, str):
            images = [images]
        if isinstance(images, list):
            urls.extend(x for x in images if isinstance(x, str))
    return list(dict.fromkeys(x.strip() for x in urls if re.match(r"^https?://", x.strip())))[:24]


def _product_jsonld(content: str) -> dict:
    for node in _jsonld(content):
        types = node.get("@type")
        types = types if isinstance(types, list) else [types]
        if any(str(value).lower() == "product" for value in types):
            offers = node.get("offers") or {}
            if isinstance(offers, list):
                offers = offers[0] if offers else {}
            rating = node.get("aggregateRating") or {}
            seller = offers.get("seller") or node.get("seller") or {}
            return {
                "description": node.get("description"),
                "sku": node.get("sku") or node.get("mpn"),
                "brand": (node.get("brand") or {}).get("name") if isinstance(node.get("brand"), dict) else node.get("brand"),
                "price": offers.get("price"),
                "currency": offers.get("priceCurrency"),
                "availability": offers.get("availability"),
                "rating": rating.get("ratingValue"),
                "reviews_count": rating.get("reviewCount"),
                "seller": seller.get("name") if isinstance(seller, dict) else seller,
            }
    return {}


def _metadata(url: str) -> dict:
    _public_url(url)
    response = requests.get(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; CentralProductRadar/2.0)",
            "Accept-Language": "es-CO,es;q=0.9,en;q=0.7",
            "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
        },
        timeout=20,
        allow_redirects=True,
    )
    response.raise_for_status()
    _public_url(response.url)
    content = response.text[:2_000_000]
    result = {"resolved_url": response.url, "gallery_urls": _gallery_from_content(content)}
    patterns = {
        "title": r'<meta[^>]+property=["\\']og:title["\\'][^>]+content=["\\']([^"\\']+)["\\']|<meta[^>]+content=["\\']([^"\\']+)["\\'][^>]+property=["\\']og:title["\\']',
        "image_url": r'<meta[^>]+(?:property|name)=["\\']og:image["\\'][^>]+content=["\\']([^"\\']+)["\\']|<meta[^>]+content=["\\']([^"\\']+)["\\'][^>]+(?:property|name)=["\\']og:image["\\']',
        "description": r'<meta[^>]+(?:property|name)=["\\']og:description["\\'][^>]+content=["\\']([^"\\']+)["\\']|<meta[^>]+content=["\\']([^"\\']+)["\\'][^>]+(?:property|name)=["\\']og:description["\\']',
    }
    for key, pattern in patterns.items():
        match = re.search(pattern, content, re.I)
        if match:
            result[key] = html.unescape(match.group(1) or match.group(2)).strip()
    price, price_currency = _parse_price(content)
    if price is not None:
        result["price"] = price
    if price_currency:
        result["currency"] = price_currency
    result.update({k: v for k, v in _product_jsonld(content).items() if v not in (None, "", [])})
    if result.get("price") is None:
        try:
            result["price"] = float(result.get("price"))
        except (TypeError, ValueError):
            result["price"] = None
    if not result.get("title"):
        match = re.search(r"<title[^>]*>(.*?)</title>", content, re.I | re.S)
        if match:
            result["title"] = html.unescape(re.sub(r"\\s+", " ", match.group(1))).strip()
    return result


def _amazon_web_metadata(asin: str) -> dict:
    try:
        response = requests.get(
            "https://www.bing.com/search",
            params={"q": f'site:amazon.com/dp "{asin}"', "count": 5},
            headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/140 Safari/537.36", "Accept-Language": "en-US,en;q=0.9"},
            timeout=20,
        )
        response.raise_for_status()
        content = response.text
        result = {"resolved_url": f"https://www.amazon.com/dp/{asin}", "image_url": None, "gallery_urls": []}
        title_match = re.search(r"<h2[^>]*>(.*?)</h2>|<h3[^>]*>(.*?)</h3>", content, re.I | re.S)
        if title_match:
            title = next((x for x in title_match.groups() if x), "")
            title = re.sub(r"<[^>]+>", " ", title)
            title = re.sub(r"\\s+", " ", html.unescape(title)).strip()
            if title and title.lower() not in {"amazon.com", "amazon"}:
                result["title"] = title[:500]
        price_match = re.search(r"\\$\\s*([0-9][0-9,]*(?:\\.[0-9]{1,2})?)", content)
        if price_match:
            result["price"] = float(price_match.group(1).replace(",", ""))
            result["currency"] = "USD"
        return result
    except (requests.RequestException, ValueError):
        return {}


def import_url(url: str, category: str, title: str | None = None, price: float | None = None, currency: str = "USD", image_url: str | None = None) -> dict:
    url = url.strip()
    _public_url(url)
    platform = detect_platform(url)
    metadata = _metadata(url)
    resolved_url = metadata.get("resolved_url") or url
    _public_url(resolved_url)
    external_id = _asin(resolved_url) if platform == "amazon" else None
    if not external_id:
        path = urlparse(resolved_url).path
        match = re.search(r"/([A-Z]{2,4}-?\\d{6,})", path, re.I)
        external_id = match.group(1).upper() if match else re.sub(r"[^a-zA-Z0-9]+", "-", path.strip("/"))[:120]
    if platform == "amazon" and external_id and (not metadata.get("title") or metadata.get("price") is None or not metadata.get("image_url")):
        fallback = _amazon_web_metadata(external_id)
        for key, value in fallback.items():
            if key == "gallery_urls":
                metadata[key] = list(dict.fromkeys((metadata.get(key) or []) + value))
            elif not metadata.get(key):
                metadata[key] = value
    final_title = (title or metadata.get("title") or "").strip()
    final_image = (image_url or metadata.get("image_url") or "").strip() or None
    final_price = price if price is not None else metadata.get("price")
    final_currency = metadata.get("currency") or currency
    if not final_title:
        raise ValueError("No fue posible obtener el nombre real del producto.")
    if not final_image:
        raise ValueError("No fue posible obtener una imagen real del producto. Proporciónala manualmente para importarlo.")
    if final_price is None or float(final_price) <= 0:
        raise ValueError("No fue posible obtener el precio real. Proporciónalo manualmente para importarlo.")
    gallery = metadata.get("gallery_urls") or []
    if final_image not in gallery:
        gallery.insert(0, final_image)
    return {
        "platform": platform,
        "external_id": external_id,
        "title": final_title[:500],
        "description": str(metadata.get("description") or "").strip()[:5000] or None,
        "sku": str(metadata.get("sku") or "").strip()[:150] or None,
        "image_url": final_image,
        "gallery_urls": gallery[:24],
        "product_url": resolved_url,
        "price": float(final_price),
        "currency": str(final_currency).upper()[:10] if final_currency else "USD",
        "rating": float(metadata["rating"]) if metadata.get("rating") not in (None, "") else None,
        "reviews_count": int(float(metadata["reviews_count"])) if metadata.get("reviews_count") not in (None, "") else 0,
        "sales_estimate": None,
        "seller": {"name": metadata.get("seller")} if metadata.get("seller") else {},
        "source_metadata": {
            "import_method": "product_url",
            "metadata_source": "open_graph+jsonld",
            "original_url": url,
            "resolved_url": resolved_url,
            "brand": metadata.get("brand"),
            "availability": metadata.get("availability"),
            "gallery_urls": gallery[:24],
        },
    }
