import os
import time
from psycopg2.extras import Json

import schedule

from amazon_api import fetch_amazon_products
from analysis import score_product
from db import get_connection, upsert_product
from ingest import fetch_mercadolibre
from init_db import init_database
from notifications import send_telegram_alert
from tiktok_creator import creator_configured, sync_showcase

SEARCH_CONFIG = [
    ("accesorios", "soporte celular"),
    ("accesorios", "audifonos bluetooth"),
    ("electronica", "smartwatch"),
    ("electronica", "teclado mecanico"),
    ("electronica", "mouse gamer"),
    ("hogar", "organizador hogar"),
    ("hogar", "lampara led"),
    ("ropa", "campera mujer"),
    ("calzado", "zapatillas urbanas"),
    ("fitness", "accesorios gimnasio"),
    ("electronica", "monitor 4k"),
    ("electronica", "webcam"),
    ("electronica", "parlante bluetooth"),
    ("electronica", "disco ssd"),
    ("electronica", "memoria micro sd"),
    ("accesorios", "cargador usb c"),
    ("accesorios", "power bank"),
    ("hogar", "camara seguridad wifi"),
    ("hogar", "aspiradora robot"),
    ("hogar", "iluminacion led"),
    ("fitness", "reloj deportivo"),
    ("fitness", "bandas resistencia"),
    ("calzado", "tenis hombre"),
    ("calzado", "tenis mujer"),
    ("electronica", "consola videojuegos"),
]
SCORE_THRESHOLD = float(os.getenv("SCORE_THRESHOLD", "50"))
AMAZON_BATCH_SIZE = int(os.getenv("AMAZON_BATCH_SIZE", "100"))
MELI_BATCH_SIZE = int(os.getenv("MELI_BATCH_SIZE", "20"))

def build_url(title: str, product_url: str | None) -> str:
    if product_url and product_url != "#":
        return product_url
    return f"https://listado.mercadolibre.com.co/{title.replace(' ', '-')}"


def expire_catalog():
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE products
                SET catalog_expires_at = catalog_batch_id + INTERVAL '48 hours'
                WHERE is_active = TRUE
                  AND source_metadata->>'seed' = 'catalogo_20_productos_2026_10'
                  AND catalog_batch_id IS NOT NULL
                  AND catalog_expires_at > catalog_batch_id + INTERVAL '48 hours'
            """)
            cur.execute("""
                SELECT id
                FROM products
                WHERE is_active = TRUE
                  AND catalog_expires_at IS NOT NULL
                  AND catalog_expires_at <= NOW()
            """)
            expired_ids = [row["id"] for row in cur.fetchall()]
            if expired_ids:
                cur.execute(
                    "UPDATE products SET is_active = FALSE, updated_at = NOW() WHERE id = ANY(%s)",
                    (expired_ids,),
                )
                cur.execute(
                    "UPDATE published_cards SET is_published = FALSE, updated_at = NOW() WHERE product_id = ANY(%s)",
                    (expired_ids,),
                )
        conn.commit()
        print(f"== Productos vencidos retirados: {len(expired_ids)} ==")
        return len(expired_ids)
    finally:
        conn.close()


def save_pipeline_run(started_at, expired_products, amazon_products, mercadolibre_products, tiktok_products, telegram_prepared, errors, status="success"):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT COUNT(*) AS active_products,
                       COUNT(*) FILTER (
                           WHERE COALESCE(s.opportunity_score, 0) >= 70
                       ) AS high_opportunity
                FROM products p
                LEFT JOIN product_scores s ON s.product_id = p.id
                WHERE p.is_active = TRUE
            """)
            totals = cur.fetchone()
            cur.execute("""
                INSERT INTO pipeline_runs (
                    started_at, finished_at, status, duration_ms,
                    expired_products, active_products, high_opportunity,
                    amazon_products, mercadolibre_products, tiktok_products,
                    telegram_prepared, error_count, errors
                )
                VALUES (
                    %s, NOW(), %s,
                    EXTRACT(EPOCH FROM (NOW() - %s)) * 1000,
                    %s,%s,%s,%s,%s,%s,%s,%s,%s
                )
            """, (
                started_at, status, started_at,
                expired_products, int(totals["active_products"] or 0),
                int(totals["high_opportunity"] or 0),
                amazon_products, mercadolibre_products, tiktok_products,
                telegram_prepared, len(errors), Json(errors[:20]),
            ))
        conn.commit()
    finally:
        conn.close()


def publish_real_discounts(conn):
    """Publica únicamente productos activos con una baja real superior al 50%."""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT
                p.id, p.title, p.current_price, p.previous_price, p.currency,
                p.image_url, p.product_url, p.affiliate_url,
                p.description, p.stock, p.rating, p.reviews_count,
                pl.name AS platform, s.opportunity_score
            FROM products p
            JOIN platforms pl ON pl.id = p.platform_id
            LEFT JOIN product_scores s ON s.product_id = p.id
            WHERE p.is_active = TRUE
              AND p.current_price IS NOT NULL
              AND p.previous_price IS NOT NULL
              AND p.previous_price > p.current_price
              AND ((p.previous_price - p.current_price) / p.previous_price) > 0.50
              AND COALESCE(NULLIF(p.image_url, ''), '') <> ''
        """)
        products = cur.fetchall()
        for product in products:
            product_url = product["affiliate_url"] or product["product_url"]
            price_display = f"{product['current_price']:,.0f} {product['currency'] or 'COP'}"
            subtitle = (
                f"{product['platform']} · descuento real verificado"
            )
            cur.execute("""
                INSERT INTO published_cards (
                    product_id, title, subtitle, price_display, image_url, product_url,
                    sale_price, cost_price, profit_amount, profit_margin_pct,
                    opportunity_score, footer, accent, is_published, published_at, updated_at
                )
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,0,0,%s,%s,%s,TRUE,NOW(),NOW())
                ON CONFLICT (product_id) DO UPDATE SET
                    title=EXCLUDED.title,
                    subtitle=EXCLUDED.subtitle,
                    price_display=EXCLUDED.price_display,
                    image_url=EXCLUDED.image_url,
                    product_url=EXCLUDED.product_url,
                    sale_price=EXCLUDED.sale_price,
                    cost_price=EXCLUDED.cost_price,
                    opportunity_score=EXCLUDED.opportunity_score,
                    footer=EXCLUDED.footer,
                    accent=EXCLUDED.accent,
                    is_published=TRUE,
                    updated_at=NOW()
            """, (
                product["id"], product["title"], subtitle, price_display,
                product["image_url"], product_url, product["current_price"],
                product["current_price"], product["opportunity_score"] or 0,
                "Descuento real > 50% · Disponible en Central", "#b6f23a",
            ))
    conn.commit()
    print(f"[storefront] publicaciones automáticas >50%: {len(products)}")



def ingest_amazon(conn) -> list[int]:
    ids = []
    with conn.cursor() as cur:
        cur.execute("""
            SELECT p.external_id
            FROM products p
            JOIN platforms pl ON pl.id = p.platform_id
            WHERE pl.name = 'amazon' AND p.is_active = TRUE
        """)
        existing_ids = {str(row["external_id"]).upper() for row in cur.fetchall()}

    products = fetch_amazon_products(existing_ids, AMAZON_BATCH_SIZE)
    if not products:
        print("[amazon] Creators API sin resultados. Amazon queda como fuente opcional; se conserva el catalogo existente.")
        return ids
    print(f"[amazon] lote valido recibido: {len(products)}")
    for category, product in products:
        try:
            product_id = upsert_product(conn, "amazon", category, product)
            ids.append(product_id)
            # Las primeras 30 fichas Amazon quedan publicadas automáticamente
            # para convertir tráfico en ventas y generar atribución.
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) AS total FROM published_cards pc JOIN products p ON p.id = pc.product_id JOIN platforms pl ON pl.id = p.platform_id WHERE pl.name = 'amazon' AND pc.is_published = TRUE")
                published = int(cur.fetchone()["total"] or 0)
                if published < 30 and product.get("image_url"):
                    cur.execute("SELECT affiliate_url, product_url FROM products WHERE id = %s", (product_id,))
                    link_row = cur.fetchone() or {}
                    affiliate_link = link_row.get("affiliate_url") or link_row.get("product_url")
                    if not affiliate_link:
                        continue
                    cur.execute("""
                        INSERT INTO published_cards (
                            product_id, title, subtitle, price_display, image_url, product_url,
                            sale_price, cost_price, profit_amount, profit_margin_pct,
                            opportunity_score, footer, accent, is_published, published_at, updated_at
                        )
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,0,0,0,%s,%s,TRUE,NOW(),NOW())
                        ON CONFLICT (product_id) DO UPDATE SET
                            image_url=EXCLUDED.image_url,
                            product_url=EXCLUDED.product_url,
                            price_display=EXCLUDED.price_display,
                            sale_price=EXCLUDED.sale_price,
                            updated_at=NOW(),
                            is_published=TRUE
                    """, (
                        product_id,
                        product["title"],
                        "Oferta Amazon · compra segura en Amazon",
                        f"{product['price']:,.2f} {product['currency'] or 'USD'}",
                        product.get("image_url"),
                        affiliate_link,
                        product.get("price"),
                        product.get("price"),
                        "Amazon · enlace afiliado",
                        "#b6f23a",
                    ))
                    published += 1
            conn.commit()
            print(f"[amazon] {product['external_id']} -> {product['title']} | publicado={published <= 30}")
        except Exception as exc:
            conn.rollback()
            print(f"[amazon] error insertando {product.get('external_id')}: {exc}")
    return ids


def backfill_mongo_images(limit=150):
    from mongo_store import store_product_image
    conn = get_connection()
    rows = []
    done = 0
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, external_id, image_url, source_metadata
                FROM products
                WHERE is_active = TRUE
                  AND COALESCE(image_url, '') <> ''
                  AND COALESCE(source_metadata->>'mongo_image_id', '') = ''
                ORDER BY id
                LIMIT %s
            """, (limit,))
            rows = cur.fetchall()
            for row in rows:
                try:
                    mongo_id = store_product_image(row["image_url"], product_id=row["id"], external_id=row["external_id"])
                    if not mongo_id:
                        continue
                    metadata = dict(row["source_metadata"] or {})
                    metadata["mongo_image_id"] = mongo_id
                    cur.execute("UPDATE products SET source_metadata=%s, updated_at=NOW() WHERE id=%s", (Json(metadata), row["id"]))
                    done += 1
                except Exception as exc:
                    print(f"[mongo] backfill {row['id']}: {exc}")
        conn.commit()
    finally:
        conn.close()
    print(f"[mongo] imágenes migradas: {done}/{len(rows)}")
    return done


def run_pipeline():
    started_at = __import__("datetime").datetime.now()
    print("== Iniciando ciclo de ingesta y análisis ==")
    expired_products = expire_catalog()
    backfill_mongo_images()
    errors = []
    amazon_count = 0
    mercadolibre_count = 0
    tiktok_count = 0
    telegram_prepared = 0
    conn = get_connection()
    product_ids = []
    new_product_ids = []
    try:
        try:
            product_ids.extend(ingest_amazon(conn))
        except Exception as exc:
            errors.append(f"Amazon: {exc}")
            print(f"[amazon] ciclo abortado: {exc}")

        amazon_count = len(set(product_ids))

        for category, term in SEARCH_CONFIG:
            try:
                products = fetch_mercadolibre(term, limit=MELI_BATCH_SIZE)
            except Exception as exc:
                errors.append(f"Mercado Libre '{term}': {exc}")
                print(f"[mercadolibre] error trayendo '{term}': {exc}")
                continue
            if not products:
                print(f"[mercadolibre] sin resultados reales para '{term}'.")
                continue
            mercadolibre_count += len(products)
            for product in products:
                try:
                    with conn.cursor() as cur:
                        cur.execute("""
                            SELECT p.id
                            FROM products p
                            JOIN platforms pl ON pl.id = p.platform_id
                            WHERE pl.name = 'mercadolibre' AND p.external_id = %s
                        """, (product.get("external_id"),))
                        existed = cur.fetchone()
                    product_id = upsert_product(conn, "mercadolibre", category, product)
                    product_ids.append(product_id)
                    if not existed:
                        new_product_ids.append(product_id)
                
                except Exception as exc:
                    conn.rollback()
                    print(f"[mercadolibre] error insertando producto: {exc}")

        averages = {}
        with conn.cursor() as cur:
            cur.execute("""
                SELECT c.name AS category, p.currency, AVG(p.current_price) AS avg_price
                FROM products p
                JOIN categories c ON c.id = p.category_id
                WHERE p.is_active = TRUE AND p.current_price IS NOT NULL
                GROUP BY c.name, p.currency
            """)
            for row in cur.fetchall():
                averages[(row["category"], row["currency"])] = float(row["avg_price"] or 0)

        # Telegram solo procesa productos realmente nuevos; no repite el catálogo viejo en cada ciclo.
        for product_id in set(new_product_ids):
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT c.name AS category, p.currency
                    FROM products p
                    LEFT JOIN categories c ON c.id = p.category_id
                    WHERE p.id = %s
                """, (product_id,))
                row = cur.fetchone()
            if not row:
                continue
            score = score_product(conn, product_id, averages.get((row["category"], row["currency"]), 0))
            print(f"Producto {product_id} -> opportunity_score = {score}")
            if score >= SCORE_THRESHOLD:
                with conn.cursor() as cur:
                    cur.execute("SELECT p.title, p.current_price, p.product_url FROM products p WHERE p.id = %s", (product_id,))
                    product = cur.fetchone()
                if product:
                    telegram_prepared += 1
                    send_telegram_alert({
                        "title": product["title"],
                        "price": product["current_price"],
                        "url": build_url(product["title"], product["product_url"]),
                        "score": round(score, 1),
                    })
        publish_real_discounts(conn)
    finally:
        conn.close()

    if creator_configured():
        try:
            result = sync_showcase(limit=200)
            tiktok_count = int(result.get("synced", 0) or 0)
            print(f"[tiktok] productos sincronizados: {tiktok_count}")
        except Exception as exc:
            errors.append(f"TikTok: {exc}")
            print(f"[tiktok] error sincronizando Creator: {exc}")
    else:
        print("[tiktok] integración no configurada; se conserva el ciclo principal.")
    status = "error" if errors else "success"
    try:
        save_pipeline_run(
            started_at, expired_products, amazon_count, mercadolibre_count,
            tiktok_count, telegram_prepared, errors, status
        )
    except Exception as exc:
        print(f"[metrics] no se pudo guardar la métrica del ciclo: {exc}")
    print("== Ciclo completo ==")


def run_worker():
    print("Esperando a que la base de datos esté lista...")
    time.sleep(5)
    init_database()
    run_pipeline()
    schedule.every(2).hours.do(run_pipeline)
    print("== Worker activo: próximo ciclo automático en 2 horas. ==")
    while True:
        schedule.run_pending()
        time.sleep(30)


if __name__ == "__main__":
    run_worker()
