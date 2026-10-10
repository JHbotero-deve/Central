import html
import io
import os
import re
import time
from urllib.parse import urlparse

import requests
from PIL import Image, ImageOps, UnidentifiedImageError

from analysis import score_product
from db import get_connection, upsert_product
from url_import import import_url

POLL_INTERVAL = int(os.getenv("TELEGRAM_POLL_INTERVAL", "3"))
API_BASE = "https://api.telegram.org"
ALLOWED_PLATFORMS = {"mercadolibre", "amazon", "aliexpress", "personal"}
ALLOWED_CATEGORIES = {"ropa", "calzado", "accesorios", "electronica", "hogar", "fitness", "otros"}


def _token():
    return os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("BOT_TOKEN") or os.getenv("TELEGRAM_TOKEN")


def _allowed_chat(chat_id):
    configured = os.getenv("TELEGRAM_CHAT_ID") or os.getenv("CHAT_ID")
    if not configured:
        print("[telegram-bot] Bot bloqueado: TELEGRAM_CHAT_ID no está configurado.")
        return False
    return str(chat_id) == str(configured).strip()


def _send(token, chat_id, text):
    try:
        r = requests.post(
            f"{API_BASE}/bot{token}/sendMessage",
            json={
                "chat_id": chat_id,
                "text": text[:4096],
                "parse_mode": "HTML",
                "disable_web_page_preview": False,
            },
            timeout=10,
        )
        payload = r.json()
        if not r.ok or not payload.get("ok"):
            print(f"[telegram-bot] send rejected: {payload.get('description', 'respuesta inválida')}")
            return False
        return True
    except (requests.RequestException, ValueError) as exc:
        print(f"[telegram-bot] send error: {type(exc).__name__}")
        return False


def _format_product(p):
    title = html.escape(str(p.get("title") or "Sin título")[:90])
    price = p.get("current_price")
    currency = html.escape(str(p.get("currency") or ""))
    platform = html.escape(str(p.get("platform") or "N/D"))
    category = html.escape(str(p.get("category") or "N/D"))
    rating = p.get("rating")
    reviews = p.get("reviews_count")
    sales = p.get("sales_estimate")
    opportunity = p.get("opportunity_score")
    price_score = p.get("price_score")
    demand_score = p.get("demand_score")
    trend_score = p.get("trend_score")
    url = str(p.get("product_url") or "").strip()

    lines = [
        f"<b>{title}</b>",
        f"Precio: {price if price is not None else 'N/D'} {currency}".strip(),
        f"Oportunidad: {round(float(opportunity), 1) if opportunity is not None else 'N/D'}/100",
        (
            "Modelo: "
            f"precio {round(float(price_score), 1) if price_score is not None else 'N/D'}, "
            f"demanda {round(float(demand_score), 1) if demand_score is not None else 'N/D'}, "
            f"tendencia {round(float(trend_score), 1) if trend_score is not None else 'N/D'}"
        ),
        f"Rating: {rating if rating is not None else 'N/D'} | Reseñas: {reviews if reviews is not None else 'N/D'}",
        f"Ventas estimadas: {sales if sales is not None else 'N/D'}",
        f"Plataforma: {platform}",
        f"Categoría: {category}",
    ]
    parsed = urlparse(url)
    if parsed.scheme in ("http", "https") and parsed.netloc:
        lines.append(f'<a href="{html.escape(url, quote=True)}">Ver producto</a>')
    return "\n".join(lines)


def _send_product(token, chat_id, product):
    image_url = str(product.get("image_url") or "").strip()
    text = _format_product(product)
    if image_url.startswith(("http://", "https://")):
        try:
            image_response = requests.get(
                image_url,
                headers={
                    "User-Agent": "Mozilla/5.0 (compatible; CentralTelegram/1.0)",
                    "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
                },
                timeout=15,
                allow_redirects=True,
            )
            image_response.raise_for_status()
            data = image_response.content
            if data and len(data) <= 10 * 1024 * 1024:
                with Image.open(io.BytesIO(data)) as source:
                    source.seek(0)
                    source.load()
                    # Telegram puede rechazar fotos extremas aunque estén en JPEG.
                    # Respetar orientación EXIF y encajar el producto en un lienzo cuadrado.
                    image = ImageOps.exif_transpose(source)
                    if image.mode in ("RGBA", "LA") or "transparency" in image.info:
                        rgba = image.convert("RGBA")
                        background = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
                        background.alpha_composite(rgba)
                        image = background.convert("RGB")
                    else:
                        image = image.convert("RGB")
                    image.thumbnail((1000, 1000), Image.Resampling.LANCZOS)
                    canvas = Image.new("RGB", (1024, 1024), "white")
                    canvas.paste(image, ((1024 - image.width) // 2, (1024 - image.height) // 2))
                    output = io.BytesIO()
                    canvas.save(output, format="JPEG", quality=88, optimize=True)
                    normalized = output.getvalue()
                r = requests.post(
                    f"{API_BASE}/bot{token}/sendPhoto",
                    data={"chat_id": str(chat_id), "caption": text[:1024], "parse_mode": "HTML"},
                    files={"photo": ("product.jpg", normalized, "image/jpeg")},
                    timeout=25,
                )
                payload = r.json()
                if r.ok and payload.get("ok"):
                    return True
                print(f"[telegram-bot] sendPhoto upload rejected: {payload.get('description', 'respuesta inválida')}")
            else:
                print("[telegram-bot] imagen omitida: vacía o supera 10 MB")
        except (requests.RequestException, ValueError, OSError, UnidentifiedImageError) as exc:
            print(f"[telegram-bot] image upload error: {type(exc).__name__}")
    return _send(token, chat_id, text)


def _top_products(limit=5):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT p.title, p.current_price, p.currency, p.product_url, p.image_url,
                       p.rating, p.reviews_count, p.sales_estimate,
                       pl.name AS platform, c.name AS category,
                       COALESCE(s.price_score, 0) AS price_score,
                       COALESCE(s.demand_score, 0) AS demand_score,
                       COALESCE(s.trend_score, 0) AS trend_score,
                       COALESCE(s.opportunity_score, 0) AS opportunity_score
                FROM products p
                JOIN platforms pl ON pl.id = p.platform_id
                LEFT JOIN categories c ON c.id = p.category_id
                LEFT JOIN product_scores s ON s.product_id = p.id
                WHERE p.is_active = TRUE
                  AND p.is_blocked = FALSE
                ORDER BY COALESCE(s.opportunity_score, 0) DESC, p.updated_at DESC
                LIMIT %s
                """,
                (limit,),
            )
            return cur.fetchall()
    finally:
        conn.close()


def _catalog_products(limit=20, offset=0):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT p.title, p.current_price, p.currency, p.product_url, p.image_url,
                       p.rating, p.reviews_count, p.sales_estimate,
                       pl.name AS platform, c.name AS category,
                       COALESCE(s.price_score, 0) AS price_score,
                       COALESCE(s.demand_score, 0) AS demand_score,
                       COALESCE(s.trend_score, 0) AS trend_score,
                       COALESCE(s.opportunity_score, 0) AS opportunity_score
                FROM products p
                JOIN platforms pl ON pl.id = p.platform_id
                LEFT JOIN categories c ON c.id = p.category_id
                LEFT JOIN product_scores s ON s.product_id = p.id
                WHERE p.is_active = TRUE
                  AND p.is_blocked = FALSE
                  AND pl.name IN ('personal', 'mercadolibre', 'amazon', 'aliexpress')
                ORDER BY p.id ASC
                LIMIT %s OFFSET %s
                """,
                (limit, offset),
            )
            return cur.fetchall()
    finally:
        conn.close()


def _search_products(term, limit=8):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT p.title, p.current_price, p.currency, p.product_url, p.image_url,
                       p.rating, p.reviews_count, p.sales_estimate,
                       pl.name AS platform, c.name AS category,
                       COALESCE(s.price_score, 0) AS price_score,
                       COALESCE(s.demand_score, 0) AS demand_score,
                       COALESCE(s.trend_score, 0) AS trend_score,
                       COALESCE(s.opportunity_score, 0) AS opportunity_score
                FROM products p
                JOIN platforms pl ON pl.id = p.platform_id
                LEFT JOIN categories c ON c.id = p.category_id
                LEFT JOIN product_scores s ON s.product_id = p.id
                WHERE p.is_active = TRUE
                  AND p.is_blocked = FALSE
                  AND p.title ILIKE %s
                ORDER BY COALESCE(s.opportunity_score, 0) DESC
                LIMIT %s
                """,
                (f"%{term}%", limit),
            )
            return cur.fetchall()
    finally:
        conn.close()


def _add_url(argument):
    parts = [part.strip() for part in argument.split("|")]
    if len(parts) < 2:
        return None, "Uso: /agregar categoría|url|precio|título|imagen", None

    category, url = parts[0].lower(), parts[1]
    if category not in ALLOWED_CATEGORIES:
        return None, "Categoría no válida.", None

    try:
        price = float(parts[2]) if len(parts) > 2 and parts[2] else None
        product = import_url(
            url,
            category,
            title=parts[3] if len(parts) > 3 and parts[3] else None,
            price=price,
            image_url=parts[4] if len(parts) > 4 and parts[4] else None,
        )
        if product["platform"] not in ALLOWED_PLATFORMS:
            return None, "Plataforma no habilitada para importación.", None

        conn = get_connection()
        try:
            product_id = upsert_product(conn, product["platform"], category, product)
            score = None
            if product.get("price") is not None:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT AVG(p.current_price) AS category_avg
                        FROM products p
                        JOIN categories c ON c.id = p.category_id
                        WHERE c.name = %s AND p.currency = %s
                          AND p.current_price IS NOT NULL AND p.is_active = TRUE
                        """,
                        (category, product["currency"]),
                    )
                    row = cur.fetchone()
                score = score_product(conn, product_id, float(row["category_avg"] or product["price"]))
            return product_id, product, score
        finally:
            conn.close()
    except Exception as exc:
        print(f"[telegram-bot] url import error: {exc}")
        return None, "No fue posible agregar el producto desde la URL.", None


def _extract_urls(text):
    return list(dict.fromkeys(re.findall(r"https?://[^\s<>]+", text or "")))


def _category_from_text(text):
    value = (text or "").lower()
    groups = {
        "calzado": ("tenis", "zapatilla", "zapato", "sneaker"),
        "ropa": ("camiseta", "camisa", "pantalon", "jean", "pijama", "chaqueta"),
        "electronica": ("celular", "audifono", "audífono", "smartwatch", "mouse", "teclado", "monitor", "ssd", "webcam", "consola"),
        "hogar": ("lampara", "lámpara", "organizador", "aspiradora", "cocina"),
        "fitness": ("gimnasio", "fitness", "banda resistencia", "reloj deportivo"),
        "accesorios": ("cargador", "power bank", "soporte celular", "mochila"),
    }
    for category, terms in groups.items():
        if any(term in value for term in terms):
            return category
    return "otros"


def _ingest_telegram_url(url, context=""):
    category = _category_from_text(context)
    try:
        product = import_url(url, category)
        if product["platform"] not in {"amazon", "mercadolibre", "tiktok", "aliexpress"}:
            return None, "Fuente no habilitada."
        conn = get_connection()
        try:
            product_id = upsert_product(conn, product["platform"], category, product)
            score = score_product(conn, product_id, float(product.get("price") or 0))
        finally:
            conn.close()
        message = (
            f"<b>Producto capturado</b> · ID {product_id}\n"
            f"{html.escape(product['title'])}\n"
            f"Fuente: {html.escape(product['platform'])}\n"
            f"Precio: {product['price']:,.0f} {html.escape(product['currency'])}\n"
            f"Score: {float(score):.1f}/100\n"
            f"<b>Listo para publicar:</b> /publicar {product_id}"
        )
        return product_id, message
    except Exception as exc:
        print(f"[telegram-bot] captura URL fallida: {type(exc).__name__}")
        return None, "No se pudo importar esa URL."


def _publish_product(product_id):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT p.id,p.title,p.current_price,p.currency,p.previous_price,p.image_url,
                       p.image_gallery,p.product_url,p.affiliate_url,
                       pl.name AS platform,s.opportunity_score
                FROM products p
                JOIN platforms pl ON pl.id=p.platform_id
                LEFT JOIN product_scores s ON s.product_id=p.id
                WHERE p.id=%s AND p.is_active=TRUE AND p.is_blocked=FALSE
                """,
                (product_id,),
            )
            product = cur.fetchone()
            if not product:
                return None, "Producto activo no encontrado."
            image_url = product["image_url"] or ((product["image_gallery"] or [None])[0])
            product_url = product["affiliate_url"] or product["product_url"]
            if not image_url or not product_url:
                return None, "El producto necesita imagen y enlace de origen."
            discount = 0.0
            if product["previous_price"] and product["current_price"] and product["previous_price"] > product["current_price"]:
                discount = (product["previous_price"] - product["current_price"]) / product["previous_price"] * 100
            if str(product["platform"]).lower() != "personal" and discount < 1 and float(product["opportunity_score"] or 0) < 50:
                return None, "No hay una señal suficiente de oportunidad para publicar."
            price_display = f"{product['current_price']:,.0f} {product['currency'] or 'COP'}" if product["current_price"] is not None else "Consultar"
            cur.execute(
                """
                INSERT INTO published_cards (
                    product_id,title,subtitle,price_display,image_url,product_url,
                    sale_price,cost_price,profit_amount,profit_margin_pct,
                    opportunity_score,footer,accent,is_published,published_at,updated_at
                )
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,0,0,%s,%s,%s,TRUE,NOW(),NOW())
                ON CONFLICT(product_id) DO UPDATE SET
                    title=EXCLUDED.title,subtitle=EXCLUDED.subtitle,
                    price_display=EXCLUDED.price_display,image_url=EXCLUDED.image_url,
                    product_url=EXCLUDED.product_url,sale_price=EXCLUDED.sale_price,
                    cost_price=EXCLUDED.cost_price,opportunity_score=EXCLUDED.opportunity_score,
                    footer=EXCLUDED.footer,accent=EXCLUDED.accent,
                    is_published=TRUE,updated_at=NOW()
                RETURNING id
                """,
                (
                    product["id"],product["title"],
                    f"{product['platform']} · producto verificado",
                    price_display,image_url,product_url,
                    product["current_price"],product["current_price"],
                    float(product["opportunity_score"] or 0),
                    "Producto real · fuente verificada","#b6f23a"
                ),
            )
            publication_id=cur.fetchone()["id"]
        conn.commit()
        return publication_id, f"Publicado correctamente. Tarjeta {publication_id}."
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _model_product(argument):
    parts = [part.strip() for part in argument.split("|")]
    if len(parts) < 10:
        return None, "Uso: plataforma|categoría|id|título|precio|url|rating|reseñas|ventas|imagen"
    platform, category = parts[0].lower(), parts[1].lower()
    if platform not in ALLOWED_PLATFORMS or category not in ALLOWED_CATEGORIES:
        return None, "Plataforma o categoría no permitida."
    try:
        product = {
            "external_id": parts[2],
            "title": parts[3],
            "price": float(parts[4]),
            "currency": "COP" if platform in {"mercadolibre", "aliexpress"} else "USD",
            "product_url": parts[5],
            "rating": float(parts[6]) if parts[6] else None,
            "reviews_count": int(parts[7] or 0),
            "sales_estimate": int(parts[8] or 0),
            "image_url": parts[9] or None,
        }
        conn = get_connection()
        try:
            product_id = upsert_product(conn, platform, category, product)
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT AVG(p.current_price) AS category_avg
                    FROM products p
                    JOIN categories c ON c.id = p.category_id
                    WHERE c.name = %s AND p.currency = %s
                      AND p.current_price IS NOT NULL AND p.is_active = TRUE
                    """,
                    (category, product["currency"]),
                )
                row = cur.fetchone()
            score = score_product(conn, product_id, float(row["category_avg"] or product["price"]))
            return product_id, score
        finally:
            conn.close()
    except Exception as exc:
        return None, str(exc)


def _handle(token, chat_id, text):
    command, _, argument = text.partition(" ")
    command = command.lower().strip()

    if command in ("/start", "/help"):
        return _send(token, chat_id, (
            "<b>Radar de Producto</b>\n\n"
            "/productos — mostrar los 20 productos del catálogo\n"
            "/top — oportunidades con mayor score\n"
            "/buscar producto — buscar en los datos modelados\n"
            "/modelar — registrar y puntuar un producto\n"
            "/agregar — importar un producto desde Amazon, Mercado Libre o AliExpress por URL\n"
            "/publicar ID — publicar un producto validado\n"
            "También puedes enviar una URL sola: Central la captura y la deja lista para publicar.\n"
            "/estado — estado del catálogo\n"
            "/help — ayuda"
        ))

    if command in ("/productos", "/catalogo"):
        try:
            page = max(1, min(int(argument.strip() or "1"), 500))
        except ValueError:
            return _send(token, chat_id, "Uso: /productos 1 (cada página muestra 20 productos).")
        page_size = 20
        products = _catalog_products(page_size, (page - 1) * page_size)
        if not products:
            return _send(token, chat_id, f"No hay productos en la página {page}. Prueba /productos 1.")
        _send(token, chat_id, f"<b>Catálogo Central · página {page}</b>\\nProductos mostrados: {len(products)}\\nSiguiente página: /productos {page + 1}")
        for i, product in enumerate(products, (page - 1) * page_size + 1):
            product["title"] = f"{i}. {product['title']}"
            _send_product(token, chat_id, product)
        return True

    if command == "/top":
        products = _top_products()
        if not products:
            return _send(token, chat_id, "No hay oportunidades disponibles en la base de datos.")
        _send(token, chat_id, "<b>Top oportunidades</b>")
        for i, product in enumerate(products, 1):
            product["title"] = f"{i}. {product['title']}"
            _send_product(token, chat_id, product)
        return True

    if command == "/buscar":
        term = argument.strip()
        if not term:
            return _send(token, chat_id, "Uso: /buscar zapatillas")
        products = _search_products(term)
        if not products:
            return _send(token, chat_id, f"No encontré productos modelados para: {html.escape(term)}")
        _send(token, chat_id, f"<b>Resultados: {html.escape(term)}</b>")
        for product in products:
            _send_product(token, chat_id, product)
        return True

    if command == "/agregar":
        result, payload, score = _add_url(argument.strip())
        if result is None:
            return _send(token, chat_id, f"<b>Error de importación</b>\n{html.escape(str(payload))}")
        score_text = f"Score: {float(score):.1f}/100" if score is not None else "Score: pendiente (sin precio)"
        message = (
            f"<b>Producto agregado</b>\n{html.escape(payload['title'])}\n"
            f"Plataforma: {html.escape(payload['platform'])}\n{score_text}\n"
            f'<a href="{html.escape(payload["product_url"], quote=True)}">Abrir producto original</a>'
        )
        if payload.get("image_url"):
            message += f'\nImagen: <a href="{html.escape(payload["image_url"], quote=True)}">ver imagen</a>'
        return _send(token, chat_id, message)

    if command == "/modelar":
        result, error = _model_product(argument.strip())
        if result is None:
            return _send(token, chat_id, f"<b>Error de modelado</b>\n{html.escape(str(error))}")
        return _send(token, chat_id, f"<b>Producto modelado</b>\nID: {result}\nOportunidad: {float(error):.1f}/100")

    if command == "/publicar":
        try:
            product_id = int(argument.strip())
        except ValueError:
            return _send(token, chat_id, "Uso: /publicar ID")
        result, message = _publish_product(product_id)
        if result is None:
            return _send(token, chat_id, f"<b>No publicado</b>\n{html.escape(message)}")
        return _send(token, chat_id, f"<b>{html.escape(message)}</b>")

    if command == "/estado":
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) AS total FROM products WHERE is_active = TRUE")
                total = cur.fetchone()["total"]
                cur.execute(
                    """
                    SELECT COUNT(*) AS modeled
                    FROM products p
                    JOIN product_scores s ON s.product_id = p.id
                    WHERE p.is_active = TRUE
                    """
                )
                modeled = cur.fetchone()["modeled"]
            return _send(token, chat_id, f"<b>Estado del catálogo</b>\nProductos activos: {total}\nProductos modelados: {modeled}")
        finally:
            conn.close()

    return _send(token, chat_id, "Comando no reconocido. Usa /help.")


def _clear_webhook(token):
    try:
        response = requests.post(
            f"{API_BASE}/bot{token}/deleteWebhook",
            json={"drop_pending_updates": False},
            timeout=10,
        )
        payload = response.json()
        if not response.ok or not payload.get("ok"):
            print(f"[telegram-bot] no se pudo limpiar webhook: {payload.get('description', 'respuesta inválida')}")
            return False
        return True
    except (requests.RequestException, ValueError) as exc:
        print(f"[telegram-bot] error limpiando webhook: {type(exc).__name__}")
        return False


def _acquire_polling_lock():
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT pg_try_advisory_lock(%s) AS locked", (834271,))
            locked = bool(cur.fetchone()["locked"])
        if not locked:
            conn.close()
            return None
        return conn
    except Exception:
        conn.close()
        raise


def run_bot():
    token = _token()
    if not token:
        print("[telegram-bot] Bot deshabilitado: falta TELEGRAM_BOT_TOKEN.")
        return
    if not (os.getenv("TELEGRAM_CHAT_ID") or os.getenv("CHAT_ID")):
        print("[telegram-bot] Bot deshabilitado: falta TELEGRAM_CHAT_ID.")
        return

    try:
        lock_conn = _acquire_polling_lock()
    except Exception as exc:
        print(f"[telegram-bot] no se pudo adquirir el bloqueo de polling: {type(exc).__name__}")
        return
    if lock_conn is None:
        print("[telegram-bot] otra instancia mantiene el bloqueo de polling; esta instancia termina.")
        return

    try:
        _clear_webhook(token)
        offset = None
        print("[telegram-bot] Bot interactivo iniciado.")
        while True:
            try:
                params = {"timeout": 25}
                if offset is not None:
                    params["offset"] = offset
                response = requests.get(f"{API_BASE}/bot{token}/getUpdates", params=params, timeout=35)
                response.raise_for_status()
                payload = response.json()
                if not payload.get("ok"):
                    raise RuntimeError(payload.get("description", "respuesta inválida"))
                for update in payload.get("result", []):
                    offset = update["update_id"] + 1
                    message = update.get("message") or update.get("channel_post") or {}
                    chat = message.get("chat") or {}
                    text = message.get("text") or message.get("caption") or ""
                    chat_id = chat.get("id")
                    if chat_id is None or not _allowed_chat(chat_id):
                        continue
                    if text.startswith("/"):
                        _handle(token, chat_id, text)
                        continue
                    for url in _extract_urls(text)[:3]:
                        clean_url = url.rstrip(".,);]}")
                        _, result = _ingest_telegram_url(clean_url, text)
                        _send(token, chat_id, result)
            except requests.HTTPError as exc:
                response = getattr(exc, "response", None)
                status = response.status_code if response is not None else "?"
                if status == 409:
                    print("[telegram-bot] Telegram devolvió 409: hay otro consumidor de getUpdates. Se detiene esta instancia.")
                    return
                print(f"[telegram-bot] polling HTTP error: {status}")
                time.sleep(max(POLL_INTERVAL, 5))
            except (requests.RequestException, ValueError, RuntimeError) as exc:
                print(f"[telegram-bot] polling error: {type(exc).__name__}")
                time.sleep(max(POLL_INTERVAL, 5))
    finally:
        try:
            lock_conn.close()
        except Exception:
            pass


async def handle_telegram_product_search(update, context):
    query = update.message.text.replace("/buscar", "").strip()
    if not query:
        return await update.message.reply_text("Por favor ingresa un término de búsqueda válido, ej: /buscar iPhone")
    
    results = fetch_mercadolibre(query, limit=5)
    if not results:
        return await update.message.reply_text("No se encontraron productos activos para este término.")
    
    saved_count = len(results)
    await update.message.reply_text(f"¡Éxito! Se han procesado e ingresado {saved_count} productos a la tienda central.")

async def handle_telegram_product_search(update, context):
    try:
        query = update.message.text.replace("/buscar", "").strip()
        if not query:
            return await update.message.reply_text("Ingresa un término válido.")
        results = fetch_mercadolibre(query, limit=5)
        if not results:
            return await update.message.reply_text("No se encontraron productos.")
        saved_count = len(results)
        await update.message.reply_text(f"¡Éxito! Se ingresaron {saved_count} productos.")
    except Exception:
        await update.message.reply_text("Ocurrió un error interno.")
