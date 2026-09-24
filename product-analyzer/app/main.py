import os
import threading
import time

import schedule
import uvicorn

from analysis import score_product
from api import app as api_app
from db import get_connection, upsert_product
from ingest import fetch_amazon, fetch_mercadolibre, fetch_tiktok
from init_db import init_database
from notifications import send_telegram_alert


SEARCH_CONFIG = [
    ("ropa", "remera hombre"),
    ("ropa", "campera mujer"),
    ("calzado", "zapatillas urbanas"),
]
SCORE_THRESHOLD = float(os.getenv("SCORE_THRESHOLD", "50"))


def build_url(platform: str, title: str, product_url: str | None) -> str:
    """Devuelve exclusivamente la URL real almacenada; no inventa búsquedas de producto."""
    if product_url and product_url.startswith(("http://", "https://")):
        return product_url
    return ""


def start_api_server() -> None:
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(api_app, host="0.0.0.0", port=port)


def run_pipeline() -> None:
    print("Esperando a que la base de datos esté lista...")
    time.sleep(5)
    print("== Iniciando ciclo de ingesta y análisis ==")

    conn = get_connection()
    product_ids: list[int] = []

    source_functions = [
        ("mercadolibre", fetch_mercadolibre),
        ("amazon", fetch_amazon),
        ("tiktok", fetch_tiktok),
    ]

    try:
        for category, term in SEARCH_CONFIG:
            for platform_name, fetch_fn in source_functions:
                try:
                    products = fetch_fn(term)
                except Exception as exc:
                    print(f"[{platform_name}] error trayendo '{term}': {exc}")
                    continue

                if not products:
                    print(f"[{platform_name}] sin resultados reales para '{term}'.")
                    continue

                valid_products = [
                    product
                    for product in products
                    if product.get("external_id")
                    and product.get("title")
                    and product.get("price") not in (None, 0, "0", "0.0")
                ]
                print(f"[{platform_name}] {len(valid_products)} productos válidos para guardar.")

                for product in valid_products:
                    try:
                        product_ids.append(
                            upsert_product(conn, platform_name, category, product)
                        )
                    except Exception as exc:
                        print(f"Error insertando producto de {platform_name}: {exc}")

        averages: dict[tuple[str, str], float] = {}
        with conn.cursor() as cur:
            cur.execute(
                "SELECT c.name AS category, p.currency, AVG(p.current_price) AS avg_price "
                "FROM products p JOIN categories c ON c.id = p.category_id "
                "WHERE p.is_active = TRUE AND p.current_price IS NOT NULL "
                "GROUP BY c.name, p.currency"
            )
            for row in cur.fetchall():
                averages[(row["category"], row["currency"])] = float(row["avg_price"] or 0)

        for product_id in set(product_ids):
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT c.name AS category, p.currency "
                    "FROM products p "
                    "LEFT JOIN categories c ON c.id = p.category_id "
                    "WHERE p.id = %s",
                    (product_id,),
                )
                row = cur.fetchone()

            if not row:
                continue

            score = score_product(
                conn,
                product_id,
                averages.get((row["category"], row["currency"]), 0),
            )
            print(f"Producto {product_id} -> opportunity_score = {score}")

            if score < SCORE_THRESHOLD:
                continue

            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT
                        p.external_id,
                        p.title,
                        p.current_price AS price,
                        p.currency,
                        p.rating,
                        p.reviews_count,
                        p.sales_estimate,
                        p.product_url,
                        p.affiliate_url,
                        c.name AS category,
                        pl.name AS platform
                    FROM products p
                    JOIN platforms pl ON pl.id = p.platform_id
                    LEFT JOIN categories c ON c.id = p.category_id
                    WHERE p.id = %s
                    """,
                    (product_id,),
                )
                product = cur.fetchone()

            if product:
                product["score"] = round(score, 1)
                product["url"] = build_url(
                    product["platform"],
                    product["title"],
                    product["product_url"],
                )
                send_telegram_alert(product)

    finally:
        conn.close()

    print("== Ciclo completo ==")


if __name__ == "__main__":
    init_database()
    threading.Thread(target=start_api_server, daemon=True).start()
    run_pipeline()

    schedule.every(6).hours.do(run_pipeline)
    while True:
        schedule.run_pending()
        time.sleep(30)
