import time
import schedule

from db import get_connection, upsert_product
from ingest import fetch_mercadolibre, fetch_amazon, fetch_tiktok
from analysis import score_product
from notifications import send_telegram_alert
from init_db import init_database

CATEGORY = "ropa"
SEARCH_TERMS = ["remera hombre", "campera mujer", "zapatillas urbanas"]


def run_pipeline():
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
                pid = upsert_product(conn, platform_name, CATEGORY, product)
                product_ids.append(pid)

    # Calcular precio promedio de la categoría para el scoring
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

        if score >= 90:
            # Obtener detalles del producto para la alerta
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT title, current_price, product_url FROM products WHERE id = %s",
                    (pid,)
                )
                row = cur.fetchone()
                if row:
                    product_info = {
                        "title": row["title"],
                        "price": row["current_price"],
                        "url": row["product_url"],
                        "score": round(score, 1)
                    }
                    send_telegram_alert(product_info)

    conn.close()
    print("== Ciclo completo ==")


if __name__ == "__main__":
    from init_db import init_database
    init_database()  # Inicializa las tablas
    run_pipeline()  # corre una vez al iniciar
# 3. Repetir cada 6 horas para mantener precios e histórico actualizados
schedule.every(6).hours.do(run_pipeline)

while True:
    schedule.run_pending()
    time.sleep(30)
