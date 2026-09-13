import os
import requests

def send_telegram_alert(product_info):
    '''
    Envía una notificación a Telegram cuando un producto supera el score crítico.
    product_info: dict con title, price, url, score
    '''
    bot_token = os.getenv('BOT_TOKEN')
    chat_id = os.getenv('CHAT_ID')

    if not bot_token or not chat_id:
        print('[telegram] Error: BOT_TOKEN o CHAT_ID no configurados en el .env')
        return False

    # Formateamos el mensaje para que se vea profesional en el celular
    message = (
        f"🚀 *¡OPORTUNIDAD DETECTADA!*\n\n"
        f"📦 *Producto:* {product_info['title']}\n"
        f"💰 *Precio:* {product_info['price']}\n"
        f"⭐ *Score:* {product_info['score']}/100\n\n"
        f"🔗 [Ir al producto]({product_info['url']})"
    )

    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "Markdown"
    }

    try:
        r = requests.post(url, json=payload, timeout=10)
        if r.ok:
            print(f'[telegram] Alerta enviada con éxito para: {product_info["title"]}')
            return True
        else:
            print(f'[telegram] Error al enviar: {r.text}')
            return False
    except Exception as e:
        print(f'[telegram] Error de conexión: {e}')
        return False
