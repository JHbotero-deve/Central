# Analizador de Productos (Mercado Libre / Amazon / TikTok Shop)

Base técnica para el proyecto: análisis y comparación de productos de moda entre
plataformas, con histórico de precios y un scoring de "oportunidad" por producto.

## Cómo correrlo

```bash
docker compose up --build
```

Esto levanta:
- **db**: Postgres 16 con el esquema ya creado (`sql/schema.sql` se ejecuta solo).
- **adminer**: interfaz web para ver la base en `http://localhost:8080`
  (sistema: PostgreSQL, servidor: `db`, usuario: `productos_user`,
  contraseña: `productos_pass`, base: `productos_db`).
- **app**: el pipeline de ingesta + análisis, corre una vez al iniciar y luego
  cada 6 horas.
- **api**: API REST (FastAPI) en `http://localhost:8000`, con documentación
  interactiva automática en `http://localhost:8000/docs`.
- **frontend**: dashboard visual en `http://localhost:3000` — muestra el
  producto con mejor score de oportunidad, el ranking completo y la
  comparación de precios entre plataformas. Si la API todavía no tiene datos
  reales cargados, muestra datos de ejemplo automáticamente.

## Endpoints de la API

| Endpoint                  | Descripción                                              |
|----------------------------|-----------------------------------------------------------|
| `GET /products`            | Lista productos, filtrable por `category` y `platform`   |
| `GET /products/{id}`       | Detalle de un producto + histórico de precios + score     |
| `GET /comparison`          | Compara precios del mismo producto entre plataformas      |
| `GET /opportunities/top`   | Top productos por `opportunity_score`                      |

## Monetización (combinada)

El proyecto soporta los tres modelos a la vez — cada producto se marca con
`monetization_type` ('affiliate' o 'dropship') según cómo se monetiza:

| Endpoint                              | Canal          | Qué hace                                        |
|----------------------------------------|----------------|--------------------------------------------------|
| `POST /monetize/click/{product_id}`    | Afiliados      | Registra el click y redirige a la plataforma real |
| `POST /monetize/click/{id}/confirm`    | Afiliados      | Marca una conversión con la comisión reportada    |
| `POST /monetize/orders`                | Dropshipping   | Crea una orden y calcula el margen automáticamente|
| `GET /monetize/orders/{user_id}`       | Dropshipping   | Historial de órdenes de un usuario                |
| `POST /monetize/subscribe`             | Suscripción    | Asigna un plan (free/pro/business) a un usuario   |
| `GET /monetize/plans`                  | Suscripción    | Lista los planes disponibles                      |
| `GET /monetize/revenue-summary`        | Los 3          | Ingresos totales por canal                        |

El dashboard (`http://localhost:3000`) ya muestra el resumen de ingresos por
canal en la sección "Ingresos por canal".

## Visor 3D de productos

Cada fila de la tabla de comparación tiene un botón **"Ver en 3D"**.

Importante — limitación real: **Mercado Libre, Amazon y TikTok Shop no
exponen modelos 3D en sus APIs**, solo fotos. Por eso el visor tiene dos modos:

1. **Por defecto**: genera una vista 3D usando la foto del producto como
   textura sobre una geometría simple según el tipo (`model_shape`:
   `garment`, `footwear`, `accessory`). Es una representación visual en
   volumen, no un escaneo 3D real del producto.
2. **Con modelo real**: para productos que controlás vos (por ejemplo, los
   de dropshipping), podés subir un `.glb`/`.gltf` real y el visor lo
   muestra con `<model-viewer>` en 3D verdadero:

```bash
curl -X PATCH http://localhost:8000/products/123/model \
  -H "Content-Type: application/json" \
  -d '{"model_url": "https://tu-storage.com/producto-123.glb"}'
```

## Estado de las integraciones

| Plataforma     | Estado                                                   |
|----------------|-----------------------------------------------------------|
| Mercado Libre  | ✅ Funciona con la API pública, sin necesidad de token    |
| Amazon         | ⏳ Cliente listo contra **Creators API**, requiere credenciales |
| TikTok Shop    | ⏳ Stub listo, requiere aprobación como partner de la API  |

**Nota sobre Amazon (revisado 2026-09-10):** Amazon discontinuó la vieja
Product Advertising API 5.0 (PAAPI5) en 2026 — ya no acepta cuentas nuevas
y el sitio de documentación quedó desactualizado. Este proyecto ya está
adaptado a su reemplazo, la **Creators API** (OAuth2 con Client ID/Secret,
en vez de firma AWS a mano), pero como es una API relativamente nueva
conviene verificar el path exacto de `SearchItems` contra la doc oficial
antes de depender de esto en producción:
https://affiliate-program.amazon.com/creatorsapi/docs/en-us/introduction

Mientras no se configuren las credenciales de Amazon/TikTok, el sistema usa
datos de ejemplo para esas dos plataformas, así podés probar todo el flujo
(guardado en base, histórico de precios, scoring) de punta a punta.

## Completar credenciales reales

**1. Copiar la plantilla:**
```bash
cp .env.example .env
```

**2. Amazon (Creators API)** — requiere ser Amazon Associate aprobado y
tener al menos 10 ventas calificadas en los últimos 30 días (subió el
requisito respecto a la vieja PAAPI5). Registrate específicamente para
Creators API en `affiliate-program.amazon.com/creatorsapi` → Onboarding,
generá tu `AMAZON_CLIENT_ID` y `AMAZON_CLIENT_SECRET` (ya no son un
Access Key/Secret Key estilo AWS) y completalos en `.env` junto con
`AMAZON_PARTNER_TAG`.

**3. TikTok Shop** — primero completá `TIKTOK_API_KEY` y `TIKTOK_API_SECRET`
en `.env` (salen de tu app en `partner.tiktokshop.com`). El `ACCESS_TOKEN` y
`SHOP_CIPHER` requieren un paso de autorización OAuth, para eso corré:

```bash
cd app
pip install -r requirements.txt   # si no lo corriste ya vía Docker
python get_tiktok_token.py --step auth
```

Esto te da un link para abrir en el navegador y autorizar la app contra tu
tienda. TikTok te redirige con `?code=XXXX` en la URL — copiá ese código y
corré:

```bash
python get_tiktok_token.py --step token --code XXXX
```

Te va a imprimir el `ACCESS_TOKEN` y el `SHOP_CIPHER` listos para pegar en
`.env` (el `shop_id` también se muestra, pero es solo de referencia: la
API 202309 identifica la tienda por `shop_cipher`, no por `shop_id`).

**4. Reiniciar los contenedores** para que tomen las nuevas variables:
```bash
docker compose up --build
```

A partir de ahí, `app/ingest.py` detecta las credenciales automáticamente y
usa las implementaciones reales (`amazon_paapi.py`, `tiktok_shop.py`) en
lugar de los datos de ejemplo.

## Despliegue en Producción (PaaS)

Para llevar este proyecto a producción usando un PaaS (Railway, Render, Fly.io) conectado a GitHub:

1. **Sincronización**: Haz `git push` de todo el proyecto a tu repositorio de GitHub.
2. **Automatización**: El archivo `.github/workflows/deploy.yml` construirá automáticamente las imágenes de Docker y las subirá al GitHub Container Registry.
3. **Configuración en PaaS**:
   - Conecta tu repo de GitHub.
   - Crea un **Volumen persistente** para el servicio `db` (mapeado a `/var/lib/postgresql/data`) para no perder tus datos.
   - Configura las **Variables de Entorno** en el panel del PaaS copiando tu archivo `.env`.
4. **Dominio**: Configura el dominio personalizado y asegúrate de que el tráfico use HTTPS.
5. **Frontend**: Actualiza la variable `API_BASE` en el frontend con la URL real de tu API en producción.

**Importante:** El esquema de la base de datos se crea automáticamente al iniciar gracias a la carpeta `sql/` mapeada en el contenedor de Postgres.

## Próximos pasos sugeridos

1. Sumar más categorías (calzado, accesorios) y más términos de búsqueda.
2. Armar un endpoint/API (FastAPI) sobre esta base para que un frontend
   consuma `product_price_comparison` y `product_scores`.
3. Definir el modelo de ingresos (afiliados / dropshipping / SaaS) para saber
   si hace falta agregar tablas de órdenes, comisiones y pasarela de pago.
