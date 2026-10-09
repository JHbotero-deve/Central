import os
import requests

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

def send_telegram_deal(product):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        return False
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    text = (
        f"🔥 **¡OFERTA EXPLOSIVA -{product.get('discount_percentage', 50)}% OFF!** 🔥\n\n"
        f"🛍️ *{product.get('title')}*\n"
        f"💰 Precio Oferta: ${product.get('price')}\n"
        f"📉 Precio Anterior: ${product.get('original_price')}\n"
        f"🏬 Plataforma: {product.get('platform', '').upper()}\n\n"
        f"👉 [Comprar Asegurado aquí]({product.get('affiliate_url')})"
    )
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "Markdown"
    }
    try:
        response = requests.post(url, json=payload, timeout=5)
        return response.status_code == 200
    except Exception:
        return False
