# Central

## Arquitectura

- Frontend estático en Vercel desde `product-analyzer/frontend`.
- API, worker y bot en Railway desde `product-analyzer/app`.
- PostgreSQL de Railway como persistencia única.
- Mercado Libre y Amazon como fuentes de ofertas verificadas por orden explícita; AliExpress y TikTok Shop se importan por URL hasta habilitar sus APIs de precios/afiliados.
- Telegram para consultas y alertas.
- Wompi para pagos de productos propios.

## Flujo

Telegram `/inyectar` → búsquedas reales de Mercado Libre y Amazon → verificación de precio actual y original (mínimo 40%) → PostgreSQL → publicaciones con caducidad a 7 días → API → Vercel. La ingesta automática del Worker queda apagada por defecto para que no busque fuentes externas sin una orden explícita; se puede habilitar con `CATALOG_AUTO_SYNC_ENABLED=true`.

AliExpress y TikTok Shop se agregan por URL desde el bot de Telegram con `/agregar categoría|URL`. Si la tienda bloquea la lectura automática, completa los datos reales: `/agregar categoría|URL|PRECIO|TÍTULO|IMAGEN_URL|MONEDA`. Amazon también admite importación por URL; las ofertas Amazon solo entran en `/inyectar` cuando Creators API devuelve precio actual y precio de referencia.

`/buscar término` consulta Amazon y AliExpress, no el catálogo de la tienda Central; los resultados son informativos y no se guardan ni publican automáticamente. `/inyectar` inicia explícitamente una búsqueda/importación de hasta 200 ofertas reales por ciclo, publica solo ofertas Amazon con precio de referencia verificable y descuento mínimo del 40%, y limita su vigencia automática a 7 días. Requiere credenciales vigentes de Amazon Creators API y puede no importar resultados si no hay ofertas elegibles. AliExpress sigue disponible para importaciones directas por URL, sin inventar ni inferir precios originales; no se inyecta automáticamente hasta contar con una API que verifique precio de referencia.

PostgreSQL es el origen de verdad para productos y publicaciones. MongoDB se usa para imágenes y auditoría, no para almacenar el catálogo.

## Publicación

Central ingresa y analiza productos. `/inyectar` publica automáticamente ofertas externas que superan la verificación del 40%; otros productos requieren publicación manual. La tienda solo muestra publicaciones activas almacenadas en PostgreSQL.

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

## Agentes CLI de Central

Desde `product-analyzer/app`, con el entorno Python y `DATABASE_URL` configurados:

```bash
python central_agents.py search "audifonos bluetooth" --limit 8
python central_agents.py audit --limit 1000
python central_agents.py ad-copy 123
```

- `search`: consulta las fuentes de búsqueda que estén configuradas y devuelve JSON con la procedencia disponible. Respeta los límites del proveedor; no intenta eludir bloqueos ni fabrica productos.
- `audit`: auditoría de solo lectura para detectar precio, imagen, título, URL y duplicados potenciales.
- `ad-copy`: genera un borrador con los datos guardados. Solo menciona descuentos si existe un precio anterior superior al actual; requiere aprobación humana y no publica automáticamente.

Comandos de Telegram: `/auditar`, `/publicidad ID` y `/agentes`. La integración usa el catálogo PostgreSQL existente. No sustituye la verificación de disponibilidad ni garantiza posicionamiento en buscadores.
