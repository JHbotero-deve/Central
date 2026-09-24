import os
import psycopg2
from urllib.parse import urlparse
from psycopg2.extras import RealDictCursor


def get_connection():
    """Abre una conexión a Postgres usando variables de entorno."""
    db_url = os.getenv("DATABASE_URL")
    if db_url:
        return psycopg2.connect(db_url, cursor_factory=RealDictCursor)

    return psycopg2.connect(
        host=os.getenv("DB_HOST", "db"),
        port=os.getenv("DB_PORT", "5432"),
        dbname=os.getenv("DB_NAME", "productos_db"),
        user=os.getenv("DB_USER", "productos_user"),
        password=os.getenv("DB_PASSWORD", "productos_pass"),
        cursor_factory=RealDictCursor,
    )

def _validate_product(platform_name: str, product: dict) -> None:
    external_id = str(product.get("external_id") or "").strip()
    title = str(product.get("title") or "").strip()
    product_url = str(product.get("product_url") or "").strip()
    price = product.get("price")
    if not external_id or not title:
        raise ValueError(f"{platform_name}: producto sin external_id o title")
    if price is None or float(price) <= 0:
        raise ValueError(f"{platform_name}: producto sin precio válido")
    if not product_url.startswith(("https://", "http://")) or not urlparse(product_url).netloc:
        raise ValueError(f"{platform_name}: producto sin URL canónica válida")

def upsert_product(conn, platform_name: str, category_name: str, product: dict):
    _validate_product(platform_name, product)
    """
    Inserta o actualiza un producto y guarda un punto en el histórico de precios.
    product debe tener: external_id, title, image_url, product_url,
    price, currency, rating, reviews_count, sales_estimate
    """
    with conn.cursor() as cur:
        cur.execute("SELECT id FROM platforms WHERE name = %s", (platform_name,))
        platform_id = cur.fetchone()["id"]

        cur.execute("SELECT id FROM categories WHERE name = %s", (category_name,))
        category_row = cur.fetchone()
        category_id = category_row["id"] if category_row else None

        cur.execute(
            """
            INSERT INTO products (
                platform_id, category_id, external_id, title, image_url,
                product_url, affiliate_url, current_price, currency, rating, reviews_count,
                sales_estimate, updated_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
            ON CONFLICT (platform_id, external_id)
            DO UPDATE SET
                title = EXCLUDED.title,
                image_url = COALESCE(EXCLUDED.image_url, products.image_url),
                product_url = EXCLUDED.product_url,
                affiliate_url = COALESCE(EXCLUDED.affiliate_url, products.affiliate_url),
                current_price = EXCLUDED.current_price,
                currency = EXCLUDED.currency,
                rating = EXCLUDED.rating,
                reviews_count = EXCLUDED.reviews_count,
                sales_estimate = EXCLUDED.sales_estimate,
                is_active = TRUE,
                updated_at = NOW()
            RETURNING id;
            """,
            (
                platform_id, category_id, product["external_id"], product["title"],
                product.get("image_url"), product.get("product_url"), product.get("affiliate_url"),
                product["price"], product.get("currency", "ARS"),
                product.get("rating"), product.get("reviews_count", 0),
                product.get("sales_estimate"),
            ),
        )
        product_id = cur.fetchone()["id"]

        cur.execute(
            "INSERT INTO price_history (product_id, price) VALUES (%s, %s)",
            (product_id, product["price"]),
        )

    conn.commit()
    return product_id


