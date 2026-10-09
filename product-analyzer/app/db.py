import hashlib
import os
import re
import unicodedata
from urllib.parse import quote

import psycopg2
from psycopg2.extras import Json, RealDictCursor
from mongo_store import store_product_image


def get_connection():
    db_url = os.getenv("DATABASE_URL", "").strip()
    if not db_url:
        raise RuntimeError("DATABASE_URL es obligatoria; Central usa PostgreSQL de Railway como unica base de datos.")
    return psycopg2.connect(db_url, cursor_factory=RealDictCursor)


def _affiliate_url(product: dict) -> str | None:
    url=(product.get("product_url") or "").strip()
    if product.get("platform")!="amazon" or not url: return None
    tag=(os.getenv("AMAZON_PARTNER_TAG") or os.getenv("AMAZON_ASSOCIATE_TAG") or "").strip()
    if not tag: return None
    result=url+("&" if "?" in url else "?")+"tag="+quote(tag,safe="")
    tracking=os.getenv("AMAZON_TRACKING_ID","").strip()
    if tracking: result+="&ascsubtag="+quote(tracking,safe="")
    return result

def _stable_external_id(platform_name: str, product: dict, category_name: str) -> str:
    """Genera una clave estable cuando la fuente no entrega un ID externo."""
    source_url = (product.get("product_url") or product.get("affiliate_url") or "").strip().lower()
    title = unicodedata.normalize("NFKC", str(product.get("title") or "")).strip().lower()
    normalized_title = re.sub(r"\s+", " ", title)
    identity = str(product.get("sku") or "").strip().lower() or source_url or (category_name.strip().lower() + ":" + normalized_title)
    digest = hashlib.sha256((platform_name.strip().lower() + ":" + identity).encode("utf-8")).hexdigest()[:32]
    return "central-" + digest


def upsert_product(conn, platform_name: str, category_name: str, product: dict):
    with conn.cursor() as cur:
        cur.execute("SELECT id FROM platforms WHERE name = %s", (platform_name,))
        platform = cur.fetchone()
        if not platform:
            raise ValueError(f"Plataforma no registrada: {platform_name}")

        cur.execute("SELECT id FROM categories WHERE name = %s", (category_name,))
        category = cur.fetchone()

        # Reutiliza productos propios por SKU o por título+categoría si el creador
        # de tarjetas no entrega un ID de origen estable.
        external_id = str(product.get("external_id") or "").strip()
        title = str(product.get("title") or "").strip()
        if platform_name.strip().lower() == "personal" and title:
            sku = str(product.get("sku") or "").strip()
            if sku:
                cur.execute(
                    "SELECT p.external_id FROM products p WHERE p.platform_id = %s AND p.is_active = TRUE AND BTRIM(COALESCE(p.sku, '')) = %s ORDER BY p.id ASC LIMIT 1",
                    (platform["id"], sku),
                )
            else:
                cur.execute(
                    "SELECT p.external_id FROM products p WHERE p.platform_id = %s AND p.is_active = TRUE AND LOWER(BTRIM(p.title)) = LOWER(BTRIM(%s)) AND p.category_id IS NOT DISTINCT FROM %s ORDER BY p.id ASC LIMIT 1",
                    (platform["id"], title, category["id"] if category else None),
                )
            existing_personal = cur.fetchone()
            if existing_personal and existing_personal.get("external_id"):
                external_id = str(existing_personal["external_id"])

        if not external_id:
            external_id = _stable_external_id(platform_name, product, category_name)

        seller_data = product.get("seller") or {}
        seller_id = None
        if seller_data.get("external_id"):
            cur.execute(
                """
                INSERT INTO sellers (platform_id, external_id, name, reputation)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (platform_id, external_id) DO UPDATE SET
                    name = COALESCE(EXCLUDED.name, sellers.name),
                    reputation = COALESCE(EXCLUDED.reputation, sellers.reputation)
                RETURNING id
                """,
                (
                    platform["id"],
                    str(seller_data["external_id"]),
                    seller_data.get("name"),
                    seller_data.get("reputation"),
                ),
            )
            seller_id = cur.fetchone()["id"]

        source_metadata = dict(product.get("source_metadata") or {})
        if product.get("model_3d_url = Column(String, nullable=True)
    image_url") and not source_metadata.get("mongo_image_id"):
            try:
                mongo_id = store_product_image(product["image_url"], platform=platform_name, external_id=external_id)
                if mongo_id:
                    source_metadata["mongo_image_id"] = mongo_id
                    print(f"[mongo] imagen guardada {platform_name}/{product.get('external_id')}")
            except Exception as exc:
                print(f"[mongo] imagen no guardada: {exc}")

        cur.execute(
            """
            INSERT INTO products (
                platform_id, category_id, seller_id, external_id, title,
                image_url, image_gallery, product_url, affiliate_url, current_price, currency, rating,
                reviews_count, sales_estimate, source_metadata,
                catalog_batch_id, catalog_expires_at, is_blocked, updated_at
            )
            VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s, NOW(), NOW() + INTERVAL '48 hours', FALSE, NOW()
            )
            ON CONFLICT (platform_id, external_id) DO UPDATE SET
                category_id = EXCLUDED.category_id,
                seller_id = COALESCE(EXCLUDED.seller_id, products.seller_id),
                title = EXCLUDED.title,
                image_url = COALESCE(EXCLUDED.image_url, products.image_url),
                image_gallery = CASE WHEN EXCLUDED.image_gallery <> '[]'::jsonb THEN EXCLUDED.image_gallery ELSE products.image_gallery END,
                product_url = COALESCE(EXCLUDED.product_url, products.product_url),
                affiliate_url = COALESCE(EXCLUDED.affiliate_url, products.affiliate_url),
                previous_price = CASE
                    WHEN EXCLUDED.current_price IS NOT NULL
                     AND products.current_price IS NOT NULL
                     AND EXCLUDED.current_price <> products.current_price
                    THEN products.current_price
                    ELSE products.previous_price
                END,
                current_price = COALESCE(EXCLUDED.current_price, products.current_price),
                currency = COALESCE(EXCLUDED.currency, products.currency),
                rating = COALESCE(EXCLUDED.rating, products.rating),
                reviews_count = COALESCE(EXCLUDED.reviews_count, products.reviews_count),
                sales_estimate = COALESCE(EXCLUDED.sales_estimate, products.sales_estimate),
                source_metadata = EXCLUDED.source_metadata,
                catalog_batch_id = NOW(),
                catalog_expires_at = NOW() + INTERVAL '48 hours',
                is_active = CASE WHEN products.is_blocked THEN FALSE ELSE TRUE END,
                updated_at = NOW()
            RETURNING id
            """,
            (
                platform["id"],
                category["id"] if category else None,
                seller_id,
                external_id,
                product["title"],
                product.get("image_url"),
                Json(product.get("gallery_urls") or ([product.get("image_url")] if product.get("image_url") else [])),
                product.get("product_url"),
                _affiliate_url(product),
                product.get("price"),
                product.get("currency") or "COP",
                product.get("rating"),
                product.get("reviews_count", 0),
                product.get("sales_estimate"),
                Json(source_metadata),
            ),
        )
        product_id = cur.fetchone()["id"]

        if product.get("price") is not None:
            cur.execute(
                "INSERT INTO price_history (product_id, price) VALUES (%s, %s)",
                (product_id, product["price"]),
            )

    conn.commit()
    return product_id
