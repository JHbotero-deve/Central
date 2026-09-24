from typing import Any

from notifications import format_product, send_telegram_alert


SCORE_THRESHOLD = 70


def send_message(text: str) -> bool:
    """Compatibilidad con el módulo histórico; el token siempre sale del entorno."""
    import os
    import requests

    bot_token = os.getenv("TELEGRAM_TOKEN") or os.getenv("BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID") or os.getenv("CHAT_ID")

    if not bot_token or not chat_id:
        print("[telegram] Credenciales no configuradas.")
        return False

    try:
        response = requests.post(
            f"https://api.telegram.org/bot{bot_token}/sendMessage",
            json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
            timeout=10,
        )
        response.raise_for_status()
        return True
    except requests.RequestException as exc:
        print(f"[telegram] Error: {exc}")
        return False


def alert_top_products(products: list[dict[str, Any]]) -> bool:
    if not products:
        return False

    sent = True
    for product in products[:5]:
        sent = send_telegram_alert(product) and sent
    return sent


def alert_high_score(product: dict[str, Any]) -> bool:
    score = float(product.get("opportunity_score", 0) or 0)
    if score < SCORE_THRESHOLD:
        return False

    return send_telegram_alert(
        {
            **product,
            "score": round(score, 1),
        }
    )
