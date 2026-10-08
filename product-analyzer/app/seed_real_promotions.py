"""
Inyección controlada de promociones reales para la tienda Central.
Despublica las tarjetas actuales y publica hasta 50 productos reales de Amazon
y 50 de Mercado Libre, sin duplicar por plataforma + external_id.
"""

from datetime import datetime

from db import get_connection, upsert_product
from amazon_api import search_products, _map_item, _map_fallback_item
from ingest import fetch_mercadolibre

AMAZON_QUERIES = [
    ("electronica", "wireless headphones"),
    ("electronica", "smart watch"),
    ("electronica", "gaming mouse"),
    ("electronica", "mechanical keyboard"),
    ("accesorios", "usb c charger"),
    ("accesorios", "power bank"),
    ("hogar", "smart home"),
    ("electronica", "fire tv stick"),
]
MELI_QUERIES = [
    "audifonos bluetooth", "smartwatch", "mouse gamer", "teclado mecanico",
    "cargador usb c", "power bank", "camara seguridad wifi", "parlante bluetooth",
]
MAX_PER_SOURCE = 50
BATCH = "REAL-PROMO-2026-10-07"


def ensure_catalog(conn):
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO platforms(name, base_url)
            VALUES ('amazon','https://www.amazon.com'),
                   ('mercadolibre','https://www.mercadolibre.com.co')
            ON CONFLICT(name) DO NOTHING
        """)
        for name in ("electronica", "accesorios", "hogar", "fitness", "otros"):
            cur.execute(
                "INSERT INTO categories(name) VALUES(%s) ON CONFLICT(name) DO NOTHING",
                (name,),
            )
    conn.commit()


def publish(conn, product_id, product, source):
    price = product.get("price")
    currency = product.get("currency") or ("USD" if source == "Amazon" else "COP")
    title = str(product.get("title") or "Producto")
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO published_cards (
                product_id,title,subtitle,price_display,image_url,product_url,
                sale_price,cost_price,profit_amount,profit_margin_pct,
                opportunity_score,footer,accent,is_published,published_at,updated_at
            )
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,0,0,0,%s,%s,TRUE,NOW(),NOW())
            ON CONFLICT(product_id) DO UPDATE SET
                title=EXCLUDED.title, subtitle=EXCLUDED.subtitle,
                price_display=EXCLUDED.price_display, image_url=EXCLUDED.image_url,
                product_url=EXCLUDED.product_url, sale_price=EXCLUDED.sale_price,
                cost_price=EXCLUDED.cost_price, footer=EXCLUDED.footer,
                accent=EXCLUDED.accent, is_published=TRUE,
                published_at=NOW(), updated_at=NOW()
        """, (
            product_id, title, f"PROMOCION REAL · {source}",
            f"{price:,.2f} {currency}" if price is not None else "Consultar",
            product.get("image_url"), product.get("product_url"), price, price,
            f"Precio verificado en {source} · {datetime.now().strftime('%Y-%m-%d')}",
            "#ff8a00" if source == "Amazon" else "#ffe600",
        ))


def amazon_products(conn):
    imported, seen = 0, set()
    with conn.cursor() as cur:
        cur.execute("""
            SELECT p.external_id FROM products p
            JOIN platforms pl ON pl.id=p.platform_id WHERE pl.name='amazon'
        """)
        seen = {str(r["external_id"]).upper() for r in cur.fetchall()}

    for category, query in AMAZON_QUERIES:
        if imported >= MAX_PER_SOURCE:
            break
        try:
            for item in search_products(query, 10):
                if imported >= MAX_PER_SOURCE:
                    break
                product = _map_item(item, category) or _map_fallback_item(item, category)
                if not product:
                    continue
                key = str(product["external_id"]).upper()
                if key in seen:
                    continue
                product["source_metadata"]["promotion_batch"] = BATCH
                product["source_metadata"]["promotion_source"] = "Amazon"
                product_id = upsert_product(conn, "amazon", category, product)
                publish(conn, product_id, product, "Amazon")
                conn.commit()
                seen.add(key)
                imported += 1
                print(f"[REAL] Amazon {imported}/{MAX_PER_SOURCE}: {product['title'][:90]}")
        except Exception as exc:
            conn.rollback()
            print(f"[REAL] Amazon '{query}' ERROR: {exc}")
    return imported


def mercado_libre_products(conn):
    imported, seen = 0, set()
    with conn.cursor() as cur:
        cur.execute("""
            SELECT p.external_id FROM products p
            JOIN platforms pl ON pl.id=p.platform_id WHERE pl.name='mercadolibre'
        """)
        seen = {str(r["external_id"]).upper() for r in cur.fetchall()}

    for query in MELI_QUERIES:
        if imported >= MAX_PER_SOURCE:
            break
        try:
            for product in fetch_mercadolibre(query, limit=15):
                if imported >= MAX_PER_SOURCE:
                    break
                key = str(product.get("external_id") or "").upper()
                if not key or key in seen:
                    continue
                product["source_metadata"]["promotion_batch"] = BATCH
                product["source_metadata"]["promotion_source"] = "Mercado Libre"
                product_id = upsert_product(conn, "mercadolibre", "electronica", product)
                publish(conn, product_id, product, "Mercado Libre")
                conn.commit()
                seen.add(key)
                imported += 1
                print(f"[REAL] Mercado Libre {imported}/{MAX_PER_SOURCE}: {product['title'][:90]}")
        except Exception as exc:
            conn.rollback()
            print(f"[REAL] Mercado Libre '{query}' ERROR: {exc}")
    return imported


def main():
    conn = get_connection()
    try:
        ensure_catalog(conn)
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE published_cards
                SET is_published=FALSE, updated_at=NOW()
                WHERE is_published=TRUE
            """)
            print(f"[REAL] Tarjetas anteriores ocultas: {cur.rowcount}")
        conn.commit()

        amazon = amazon_products(conn)
        meli = mercado_libre_products(conn)

        with conn.cursor() as cur:
            cur.execute("""
                SELECT COUNT(*) AS total
                FROM published_cards pc JOIN products p ON p.id=pc.product_id
                WHERE pc.is_published=TRUE AND p.is_active=TRUE
            """)
            total = cur.fetchone()["total"]

        print(f"REAL_PROMO_READY amazon={amazon} mercadolibre={meli} total_tienda={total}")
        if amazon == 0 and meli == 0:
            raise RuntimeError("No se pudo inyectar ningún producto real.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
