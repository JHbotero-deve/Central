import html
import os
from typing import Any

import requests


TELEGRAM_API = "https://api.telegram.org"


def _value(product: dict[str, Any], key: str, default: Any = "") -> Any:
    value = product.get(key, default)
    return default if value is None else value


def format_product(product: dict[str, Any]) -> str:
    """Construye la ficha normalizada que Telegram recibe para cada producto."""
    title = html.escape(str(_value(product, "title", "Sin título"))[:180])
    platform = html.escape(str(_value(product, "platform", "sin plataforma")))
    category = html.escape(str(_value(product, "category", "sin categoría")))
    external_id = html.escape(str(_value(product, "external_id", "sin ID")))
    currency = html.escape(str(_value(product, "currency", "")))
    price = _value(product, "price", _value(product, "current_price", "N/D"))
    score = _value(product, "score", _value(product, "opportunity_score", "N/D"))
    rating = _value(product, "rating", "N/D")
    reviews = _value(product, "reviews_count", 0)
    sales = _value(product, "sales_estimate", "N/D")
    product_url = str(_value(product, "product_url", _value(product, "url", ""))).strip()
    affiliate_url = str(_value(product, "affiliate_url", "")).strip()

    lines = [
        "<b>OPORTUNIDAD DE PRODUCTO</b>",
        "",
        f"<b>Producto:</b> {title}",
        f"<b>Plataforma:</b> {platform}",
        f"<b>Categoría:</b> {category}",
        f"<b>ID externo:</b> <code>{external_id}</code>",
        f"<b>Precio:</b> {price} {currency}".strip(),
        f"<b>Score:</b> {score}/100",
        f"<b>Rating:</b> {rating}",
        f"<b>Reseñas:</b> {reviews}",
        f"<b>Ventas estimadas:</b> {sales}",
    ]

    if product_url.startswith(("http://", "https://")):
        lines.extend(["", f'<a href="{html.escape(product_url, quote=True)}">Ver producto original</a>'])

    if affiliate_url.startswith(("http://", "https://")) and affiliate_url != product_url:
        lines.append(f'<a href="{html.escape(affiliate_url, quote=True)}">Abrir enlace monetizado</a>')

    return "\n".join(lines)


def send_telegram_alert(product_info: dict[str, Any]) -> bool:
    """Envía una ficha de producto real a Telegram usando solo variables de entorno."""
    bot_token = os.getenv("TELEGRAM_TOKEN") or os.getenv("BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID") or os.getenv("CHAT_ID")

    if not bot_token or not chat_id:
        print("[telegram] Error: TELEGRAM_TOKEN/BOT_TOKEN y TELEGRAM_CHAT_ID/CHAT_ID son obligatorios.")
        return False

    message = format_product(product_info)
    endpoint = f"{TELEGRAM_API}/bot{bot_token}/sendMessage"

    try:
        response = requests.post(
            endpoint,
            json={
                "chat_id": chat_id,
                "text": message,
                "parse_mode": "HTML",
                "disable_web_page_preview": False,
            },
            timeout=10,
        )
        response.raise_for_status()
        print(f"[telegram] Alerta enviada: {product_info.get('title', 'sin título')}")
        return True
    except requests.RequestException as exc:
        print(f"[telegram] Error de conexión/API: {exc}")
        return False
