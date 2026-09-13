import os, requests

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN","8971234981:AAGkGxbIUT6mxF6HPnATp0SZr4No0XwuJn8")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID","6008260829")
SCORE_THRESHOLD = int(os.getenv("SCORE_THRESHOLD","70"))

def send_message(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        requests.post(url,json={"chat_id":TELEGRAM_CHAT_ID,"text":text,"parse_mode":"HTML"},timeout=10)
    except Exception as e:
        print(f"[telegram] error: {e}")

def alert_top_products(products):
    if not products: return
    lines = ["🎯 <b>RADAR.PRO — Top oportunidades del dia</b>\n"]
    for i,p in enumerate(products[:5],1):
        emoji = "🥇🥈🥉🔹🔹"[i-1]
        lines.append(f"{emoji} <b>{p.get('title','')[:40]}</b>")
        lines.append(f"   Score: {round(p.get('opportunity_score',0))} pts | ${p.get('current_price',0):,.0f} | {p.get('platform','')}")
    send_message("\n".join(lines))

def alert_high_score(product):
    score = round(product.get("opportunity_score",0))
    if score < SCORE_THRESHOLD: return
    send_message(f"🚨 <b>ALERTA — Score alto</b>\n\n📦 {product.get('title','')[:50]}\n🏆 {score} pts\n💰 ${product.get('current_price',0):,.0f}\n🛒 {product.get('platform','')}")
