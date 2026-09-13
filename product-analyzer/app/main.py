import schedule

from db import get_connection, upsert_product
from ingest import fetch_mercadolibre, fetch_amazon, fetch_tiktok
from analysis import score_product
from notifications import send_telegram_alert
from init_db import init_database

CATEGORY = "ropa"
SEARCH_TERMS = ["remera hombre", "campera mujer", "zapatillas urbanas"]
AMAZON_TAG = "jh0c35-20"

def build_url(platform, title, product_url):
    if product_url and product_url != "#":
        return product_url
    q = title.replace(" ", "+")
    if platform == "amazon":
        return f"https://www.amazon.com/s?k={q}&tag={AMAZON_TAG}"
    if platform == "mercadolibre":
        return f"https://listado.mercadolibre.com.co/{title.replace(' ', '-')}"
    if platform == "tiktok":
        return f"https://www.tiktok.com/search?q={q}"
    return f"https://www.google.com/search?q={q}"

def run_pipeline():
    print("⏳ Esperando a que la base de datos esté lista...")
    time.sleep(5)
    print("== Iniciando ciclo de ingesta y análisis ==")
    conn = get_connection()
    product_ids = []

    for term in SEARCH_TERMS:
        for platform_name, fetch_fn in [
            ("mercadolibre", fetch_mercadolibre),
            ("amazon", fetch_amazon),
            ("tiktok", fetch_tiktok),
        ]:
            try:
                products = fetch_fn(term)
            except Exception as e:
                print(f"[{platform_name}] error trayendo '{term}': {e}")
                continue
            for product in products:
                try:
                    pid = upsert_product(conn, platform_name, CATEGORY, product)
                    product_ids.append(pid)
                except Exception as e:
                    print(f"Error insertando producto: {e}")

    with conn.cursor() as cur:
        cur.execute(
            "SELECT AVG(current_price) AS avg_price FROM products "
            "WHERE category_id = (SELECT id FROM categories WHERE name = %s)",
            (CATEGORY,),
        )
        avg_price = float(cur.fetchone()["avg_price"] or 0)

    for pid in set(product_ids):
        score = score_product(conn, pid, avg_price)
        print(f"Producto {pid} -> opportunity_score = {score}")
        if score >= 50:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT p.title, p.current_price, p.product_url, pl.name AS platform FROM products p JOIN platforms pl ON pl.id = p.platform_id WHERE p.id = %s",
                    (pid,)
                )
                row = cur.fetchone()
                if row:
                    url = build_url(row["platform"], row["title"], row["product_url"])
                    send_telegram_alert({
                        "title": row["title"],
                        "price": row["current_price"],
                        "url": url,
                        "score": round(score, 1)
                    })

    conn.close()
    print("== Ciclo completo ==")

if __name__ == "__main__":
    init_database()
    run_pipeline()

schedule.every(6).hours.do(run_pipeline)
while True:
    schedule.run_pending()
    time.sleep (30)
