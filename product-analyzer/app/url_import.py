import html
import ipaddress
import json
import re
import socket
from urllib.parse import urlparse

import requests

AMAZON_HOST_RE = re.compile(r"(^|\.)amazon\.[a-z.]+$", re.I)
MELI_HOST_RE = re.compile(r"(^|\.)(mercadolibre|mercadolivre)\.[a-z.]+$", re.I)
TIKTOK_HOST_RE = re.compile(r"(^|\.)tiktok(?:shop)?\.com$", re.I)
ALIEXPRESS_HOST_RE = re.compile(r"(^|\.)aliexpress\.[a-z.]+$", re.I)
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
        if not ipaddress.ip_address(address[4][0]).is_global:
            raise ValueError("La URL no apunta a un origen público permitido.")


def detect_platform(url: str) -> str:
    host = (urlparse(url).hostname or "").lower()
    if AMAZON_HOST_RE.search(host):
        return "amazon"
    if MELI_HOST_RE.search(host):
        return "mercadolibre"
    if TIKTOK_HOST_RE.search(host):
        return "tiktok"
    if ALIEXPRESS_HOST_RE.search(host):
        return "aliexpress"
    raise ValueError("La URL debe pertenecer a Amazon, Mercado Libre, TikTok Shop o AliExpress.")


def _aliexpress_affiliate_url(url: str) -> str | None:
    """Conserva los enlaces cortos promocionales; no confunde una URL normal con una afiliada."""
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower().rstrip(".")
    if host in {"s.click.aliexpress.com", "a.aliexpress.com"}:
        return url.strip()
    if ALIEXPRESS_HOST_RE.search(host) and re.search(r"(?:^|&)(?:aff_[a-z0-9_]+|aff_platform|aff_trace_key|terminal_id)=", parsed.query, re.I):
        return url.strip()
    return None


def _asin(url: str) -> str | None:
    match = ASIN_RE.search(urlparse(url).path)
    return match.group(1).upper() if match else None


def _jsonld(content: str) -> list[dict]:
    nodes = []
    for match in re.finditer(r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', content, re.I | re.S):
        try:
            data = json.loads(html.unescape(match.group(1)))
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
        values = data if isinstance(data, list) else [data]
        for value in values:
            if not isinstance(value, dict):
                continue
            nodes.append(value)
            graph = value.get("@graph")
            if isinstance(graph, list):
                nodes.extend(node for node in graph if isinstance(node, dict))
    return nodes


def _product_jsonld(content: str) -> dict:
    for node in _jsonld(content):
        types = node.get("@type")
        types = types if isinstance(types, list) else [types]
        if not any(str(value).lower() == "product" for value in types):
            continue
        offers = node.get("offers") or {}
        if isinstance(offers, list):
            offers = offers[0] if offers else {}
        rating = node.get("aggregateRating") or {}
        seller = offers.get("seller") or node.get("seller") or {}
        brand = node.get("brand")
        return {
            "description": node.get("description"),
            "sku": node.get("sku") or node.get("mpn"),
            "brand": brand.get("name") if isinstance(brand, dict) else brand,
            "price": offers.get("price"),
            "currency": offers.get("priceCurrency"),
            "availability": offers.get("availability"),
            "rating": rating.get("ratingValue"),
            "reviews_count": rating.get("reviewCount"),
            "seller": seller.get("name") if isinstance(seller, dict) else seller,
        }
    return {}


def _gallery_from_content(content: str) -> list[str]:
    urls = []
    for node in _jsonld(content):
        images = node.get("image")
        if isinstance(images, str):
            images = [images]
        if isinstance(images, list):
            urls.extend(x for x in images if isinstance(x, str))
    return list(dict.fromkeys(x.strip() for x in urls if re.match(r"^https?://", x.strip())))[:24]


def _parse_price(content: str) -> tuple[float | None, str | None]:
    for pattern, currency in (
        (r'"priceCurrency"\s*:\s*"([A-Z]{3})".{0,500}"price"\s*:\s*"?([0-9]+(?:\.[0-9]+)?)', None),
        (r'"price"\s*:\s*"?([0-9]+(?:\.[0-9]+)?)".{0,500}"priceCurrency"\s*:\s*"([A-Z]{3})"', None),
    ):
        match = re.search(pattern, content, re.I | re.S)
        if match:
            if currency is None:
                first, second = match.groups()
                if len(first) == 3:
                    currency, amount = first.upper(), second
                else:
                    amount, currency = first, second.upper()
            try:
                value = float(amount)
                if value > 0:
                    return value, currency
            except (TypeError, ValueError):
                pass
    marker = re.search(r'id=["\']corePriceDisplay_desktop_feature_div["\']', content, re.I)
    if marker:
        block = content[marker.start():marker.start() + 30000]
        match = re.search(
            r'a-price-symbol[^>]*>\s*([^<]+).*?a-price-whole[^>]*>\s*([0-9][0-9,]*).*?a-price-fraction[^>]*>\s*([0-9]{1,2})',
            block,
            re.I | re.S,
        )
        if match:
            symbol, whole, fraction = match.groups()
            code = {"$": "USD", "€": "EUR", "£": "GBP"}.get(symbol.strip())
            if code:
                return float(f"{whole.replace(',', '')}.{fraction}"), code
    return None, None


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
        "title": r'<meta[^>]+(?:property|name)=["\']og:title["\'][^>]+content=["\']([^"\']+)["\']|<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:property|name)=["\']og:title["\']',
        "image_url": r'<meta[^>]+(?:property|name)=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']|<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:property|name)=["\']og:image["\']',
        "description": r'<meta[^>]+(?:property|name)=["\']og:description["\'][^>]+content=["\']([^"\']+)["\']|<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:property|name)=["\']og:description["\']',
    }
    for key, pattern in patterns.items():
        match = re.search(pattern, content, re.I)
        if match:
            result[key] = html.unescape(match.group(1) or match.group(2)).strip()
    result.update({k: v for k, v in _product_jsonld(content).items() if v not in (None, "", [])})
    if result.get("price") is None:
        result["price"], result["currency"] = _parse_price(content)
    if not result.get("title"):
        match = re.search(r"<title[^>]*>(.*?)</title>", content, re.I | re.S)
        if match:
            result["title"] = html.unescape(re.sub(r"\s+", " ", match.group(1))).strip()
    return result


def import_url(
    url: str,
    category: str,
    title: str | None = None,
    price: float | None = None,
    currency: str = "USD",
    image_url: str | None = None,
) -> dict:
    url = url.strip()
    _public_url(url)
    platform = detect_platform(url)
    try:
        metadata = _metadata(url)
    except requests.RequestException as exc:
        # Algunas tiendas bloquean lectura automática. Solo se admite salida manual
        # cuando el usuario aportó título, precio e imagen real; no se inventan datos.
        if not (title and image_url and price is not None):
            if platform == "aliexpress":
                raise ValueError("AliExpress no entregó los metadatos. Completa nombre, precio e imagen real y vuelve a importar.") from exc
            raise
        metadata = {
            "resolved_url": url,
            "gallery_urls": [],
            "metadata_source": "manual",
        }
    resolved_url = metadata.get("resolved_url") or url
    external_id = _asin(resolved_url) if platform == "amazon" else None
    if not external_id:
        path = urlparse(resolved_url).path
        match = re.search(r"/([A-Z]{2,4}-?\d{6,})", path, re.I)
        external_id = match.group(1).upper() if match else re.sub(r"[^a-zA-Z0-9]+", "-", path.strip("/"))[:120]
    final_title = (title or metadata.get("title") or "").strip()
    final_image = (image_url or metadata.get("image_url") or "").strip() or None
    final_price = price if price is not None else metadata.get("price")
    final_currency = (currency if price is not None else metadata.get("currency")) or currency
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
        "affiliate_url": _aliexpress_affiliate_url(url) if platform == "aliexpress" else None,
        "price": float(final_price),
        "currency": str(final_currency).upper()[:10] if final_currency else "USD",
        "rating": float(metadata["rating"]) if metadata.get("rating") not in (None, "") else None,
        "reviews_count": int(float(metadata["reviews_count"])) if metadata.get("reviews_count") not in (None, "") else 0,
        "sales_estimate": None,
        "seller": {"name": metadata.get("seller")} if metadata.get("seller") else {},
        "source_metadata": {
            "import_method": "product_url",
            "metadata_source": metadata.get("metadata_source") or "open_graph+jsonld",
            "original_url": url,
            "resolved_url": resolved_url,
            "brand": metadata.get("brand"),
            "availability": metadata.get("availability"),
            "gallery_urls": gallery[:24],
        },
    }
