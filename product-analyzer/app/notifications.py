import os
import requests

# Credenciales cargadas desde .env
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

def send_telegram_alert(product_data):
    """
    Envía una alerta a Telegram si el producto es una oportunidad legendaria.
    product_data: diccionario con title, price, url y score.
    """
    if not BOT_TOKEN or not CHAT_ID:
        print("[Telegram] Saltando alerta: BOT_TOKEN o CHAT_ID no configurados en .env")
        return

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    
    # Formateo profesional del mensaje para maximizar clics
    message = (
        f"🔥 *¡OPORTUNIDAD LEGENDARIA DETECTADA!* 🔥\n\n"
        f"🏆 *Score:* {product_data['score']}/100\n"
        f"📦 *Producto:* {product_data['title']}\n"
        f"💰 *Precio:* {product_data['price']}\n\n"
        f"🚀 *¡Cómpralo antes de que se agote!*\n"
        f"👉 [IR AL PRODUCTO]({product_data['url']})"
    )
    
    payload = {
        "chat_id": CHAT_ID, 
        "text": message, 
        "parse_mode": "Markdown"
    }
    
    try:
        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()
        print(f"[Telegram] Alerta enviada: {product_data['title']}")
    except requests.exceptions.RequestException as e:
        print(f"[Telegram Error] {e}")
