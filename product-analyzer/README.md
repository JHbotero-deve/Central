# Central

## Arquitectura

- Frontend estático en Vercel desde `product-analyzer/frontend`.
- API, worker y bot en Railway desde `product-analyzer/app`.
- PostgreSQL de Railway como persistencia única.
- Amazon, Mercado Libre y TikTok Shop como fuentes según configuración.
- Telegram para consultas y alertas.
- Wompi para pagos de productos propios.

## Flujo

Fuentes → ingesta cada 2 horas → PostgreSQL → puntuación → API → Vercel.

## Publicación

Central ingresa y analiza productos. El usuario decide qué tarjetas se publican. La tienda solo muestra publicaciones activas almacenadas en PostgreSQL.

## Rutas

`/` abre Central. `/tienda` abre la tienda. `/producto/{slug}` abre una ficha publicada. `/api/*` se enruta a Railway.

## Regla de datos

No existen productos demo, datos simulados ni valores de respaldo. Si una fuente real falla, Central muestra la indisponibilidad y conserva únicamente datos persistidos válidos.

## Producción

Las credenciales reales viven en las variables de entorno de Railway y Vercel y no se almacenan en Git.

## AliExpress Open Platform (Dropshipping OAuth)

Callback URL to register in the AliExpress App Console (exactly as written):

`https://central-7ykr.vercel.app/api/v1/aliexpress/oauth/callback`

The callback is served by the Central API through the Vercel `/api/v1/*` rewrite. Visiting the URL without query parameters shows a harmless readiness page; authorization must be started from an authenticated Central admin session.

After AliExpress creates the application and assigns credentials, configure these variables on the Railway **gracious-renewal** API service:

- `ALIEXPRESS_APP_KEY`: the App Key issued by AliExpress.
- `ALIEXPRESS_APP_SECRET`: the App Secret issued by AliExpress (keep private).
- `ALIEXPRESS_CALLBACK_URL`: the exact callback URL above. If omitted, Central uses this default.
- `ALIEXPRESS_TOKEN_ENCRYPTION_KEY`: optional dedicated Fernet key. When omitted, Central reuses the existing `MELI_TOKEN_ENCRYPTION_KEY` to encrypt AliExpress tokens.

After the API redeploys, sign into Central as admin and open `/api/v1/aliexpress/oauth/start`. The route creates a random, single-use state that expires after 25 minutes and redirects to AliExpress. On return, Central exchanges the code on the server and stores access/refresh tokens encrypted in PostgreSQL; tokens are never returned to the browser. Check admin-only status at `/api/v1/aliexpress/oauth/status`.

The OAuth callback and seller authorization do not automatically grant affiliate-program permissions. AliExpress must separately approve the API groups needed for the intended Dropshipping or Affiliate use case.
