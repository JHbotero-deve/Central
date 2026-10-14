# Central — Guía de despliegue

Documento operativo para levantar Central cuando haya presupuesto (Railway Hobby u otro plan de pago).

## Arquitectura de servicios

| Servicio Railway | Rol | Start Command recomendado |
|------------------|-----|---------------------------|
| **API** (ej. `gracious-renewal`) | API FastAPI + rutas de publicaciones, OAuth, comercio | `uvicorn api:app --host 0.0.0.0 --port $PORT` |
| **Worker** (`central-worker`) | Health y, opcionalmente, sincronización programada | `uvicorn main:app --host 0.0.0.0 --port $PORT` |
| **central-telegram** | Bot de Telegram (polling) | `python telegram_alert.py` |
| **PostgreSQL** | Base de datos | Gestionado por Railway |
| **Vercel** | Frontend público y panel | Automático desde `product-analyzer/frontend` |

> El bot de Telegram **debe** ser un servicio separado (o un proceso dedicado). Los Dockerfiles actuales arrancan solo la API (`uvicorn`). Si el servicio `central-telegram` usa el mismo Dockerfile, sobrescribe el **Start Command** en Railway.
> API y Worker deben compartir `DATABASE_URL` y `MELI_TOKEN_ENCRYPTION_KEY` si se activa la ingesta programada. Telegram también necesita la misma base de datos y las credenciales de proveedores que use `/inyectar`, porque el comando ejecuta la ingesta en el servicio del bot.

---

## Variables de entorno por servicio

### 1. Servicio API / Worker

#### Obligatorias

| Variable | Descripción |
|----------|-------------|
| `DATABASE_URL` | PostgreSQL de Railway (connection string) |
| `ADMIN_API_KEY` | Clave para endpoints de administración y publicaciones |
| `PUBLIC_STORE_URL` | URL pública de la tienda, ej. `https://central-7ykr.vercel.app` |

#### Recomendadas / según fuentes

| Variable | Descripción |
|----------|-------------|
| `CENTRAL_API_BASE` | URL base de la API (para el bot y proxies de imagen) |
| `MONGO_URL` | Si se usa almacenamiento de imágenes en Mongo |
| `MONGO_DB_NAME` | Nombre de la base Mongo |
| `MELI_CLIENT_ID` | Mercado Libre OAuth |
| `MELI_CLIENT_SECRET` | Mercado Libre OAuth |
| `MELI_TOKEN_ENCRYPTION_KEY` | Clave Fernet para tokens Melí |
| `MELI_REDIRECT_URI` | `https://gracious-renewal-production-76df.up.railway.app/api/v1/meli/oauth/callback`; debe coincidir con la URI de la aplicación |
| `CATALOG_SYNC_INTERVAL_SECONDS` | Intervalo del Worker en segundos (por defecto 7200) |
| `CATALOG_AUTO_SYNC_ENABLED` | Ingresa automáticamente en segundo plano; por defecto `false`, por lo que se requiere `/inyectar` |
| `CATALOG_SYNC_MAX_PRODUCTS` | Máximo combinado por ciclo, limitado en código a 200 |
| `CATALOG_MIN_DISCOUNT_PCT` | Descuento mínimo verificable (por defecto 40) |
| `CATALOG_EXPIRY_DAYS` | Vigencia del catálogo automático en días (por defecto 7) |
| `AMAZON_CREDENTIAL_ID`, `AMAZON_CREDENTIAL_SECRET`, `AMAZON_PARTNER_TAG` | Credenciales/identificador de Creators API; necesarias para comprobar precios originales |
| `AMAZON_CREDENTIAL_VERSION` | Versión exacta asignada a la credencial: `3.1` (NA), `3.2` (EU) o `3.3` (FE); por defecto `3.1` |
| `AMAZON_MARKETPLACE` | Marketplace del tracking ID (por defecto `www.amazon.com`); el tracking ID debe pertenecer a ese mismo marketplace |
| `ALIEXPRESS_APP_KEY` | AliExpress Open Platform |
| `ALIEXPRESS_APP_SECRET` | AliExpress Open Platform |
| `ALIEXPRESS_CALLBACK_URL` | Por defecto: `https://central-7ykr.vercel.app/api/v1/aliexpress/oauth/callback` |
| `ALIEXPRESS_TOKEN_ENCRYPTION_KEY` | Opcional; si falta reutiliza `MELI_TOKEN_ENCRYPTION_KEY` |
| Credenciales Amazon / TikTok / Wompi | Según módulos habilitados |
### 2. Servicio central-telegram (bot)

#### Obligatorias

| Variable | Valor / descripción |
|----------|---------------------|
| `TELEGRAM_BOT_TOKEN` | Token de BotFather (regenerar si se expuso) |
| `TELEGRAM_CHAT_ID` | `6008260829` (chat autorizado) |
| `DATABASE_URL` | Misma PostgreSQL que la API (para leer productos y publicar) |

#### Recomendadas

| Variable | Descripción |
|----------|-------------|
| `CENTRAL_API_BASE` | URL de la API (proxy de imágenes `mongo://`) |
| `TELEGRAM_POLL_INTERVAL` | Segundos entre polls (por defecto 3) |
| `MELI_CLIENT_ID`, `MELI_CLIENT_SECRET`, `MELI_TOKEN_ENCRYPTION_KEY` | Necesarias para consultar/renovar Mercado Libre desde `/inyectar` |
| `AMAZON_CREDENTIAL_ID`, `AMAZON_CREDENTIAL_SECRET`, `AMAZON_PARTNER_TAG` | Necesarias para consultar Amazon y verificar precios de referencia |
| `AMAZON_CREDENTIAL_VERSION`, `AMAZON_MARKETPLACE` | Deben coincidir con la aplicación/credencial y Associates store donde se generó el Partner Tag |
| `CATALOG_SYNC_MAX_PRODUCTS`, `CATALOG_MIN_DISCOUNT_PCT`, `CATALOG_EXPIRY_DAYS` | Opcionales; defaults: 200, 40 y 7 |

### 3. Vercel (frontend)

| Variable | Descripción |
|----------|-------------|
| URL de la API | Rewrite `/api/*` hacia el servicio Railway de la API |
| Cualquier clave pública necesaria | No poner secretos en el frontend |

---

## Start Commands recomendados

### API
```bash
uvicorn api:app --host 0.0.0.0 --port $PORT
```

### Worker de catálogo (`central-worker`)
```bash
uvicorn main:app --host 0.0.0.0 --port $PORT
```

### Bot de Telegram (`central-telegram`)
```bash
python telegram_alert.py
```

Si el root del servicio es `product-analyzer/app`, el comando anterior es suficiente.  
Si el root es `product-analyzer`, usar:
```bash
python app/telegram_alert.py
```

En Railway: **Settings → Deploy → Start Command** y pegar el comando (no depender solo del `CMD` del Dockerfile para el bot).

---

## Checklist del día de pago (15–20 minutos)

1. **Activar plan** Railway (Hobby o superior).
2. **BotFather**
   - `/mybots` → `@CentralApp_bot` → **API Token**
   - Si el token se expuso antes: **Revoke** y generar uno nuevo.
3. **Servicio API**
   - Variables: `DATABASE_URL`, `ADMIN_API_KEY`, `PUBLIC_STORE_URL`, y las de fuentes que uses.
   - Start Command: `uvicorn api:app --host 0.0.0.0 --port $PORT`
   - Deploy y verificar `/health` o docs.
4. **Servicio central-telegram**
   - Variables:
     ```
     TELEGRAM_BOT_TOKEN=<token_nuevo>
     TELEGRAM_CHAT_ID=6008260829
     DATABASE_URL=<misma_que_API>
     CENTRAL_API_BASE=<url_de_la_API>
     MELI_CLIENT_ID=<id_oauth>
     MELI_CLIENT_SECRET=<secreto_oauth>
     MELI_TOKEN_ENCRYPTION_KEY=<misma_clave_que_API>
     AMAZON_CREDENTIAL_ID=<creators_api_id>
     AMAZON_CREDENTIAL_SECRET=<creators_api_secret>
     AMAZON_PARTNER_TAG=<tag_de_afiliado>
     AMAZON_CREDENTIAL_VERSION=<version_exacta_de_Amazon>
     AMAZON_MARKETPLACE=www.amazon.com
     ```
   - Start Command: `python telegram_alert.py`
   - Deploy.
5. **Logs del bot**  
   Buscar:
   - `token validado para @CentralApp_bot`
   - `Bot interactivo iniciado`
6. **Probar en Telegram**
   ```
   /help
   ```
   Luego pegar una URL de producto y, si corresponde:
   ```
   /publicar <ID>
   ```
7. **Frontend**  
   Confirmar que Vercel sigue apuntando a la API activa.

### Amazon Creators API / Prime

Para el filtro de ofertas de `/inyectar`, la aplicación usa Creators API oficial, con `deliveryFlags=["Prime"]`, `availability="Available"`, `condition="New"` y `minSavingPercent=40`; vuelve a calcular el descuento usando precio actual y `savingBasis`. En este modo no hay fallback a Bing/HTML: si Creators API falla o no devuelve una oferta elegible, no se inventa ni se importa una alternativa. Amazon documenta que `Prime` representa una oferta elegible para su programa Prime.

La cuenta debe estar completamente aceptada en Amazon Associates del marketplace objetivo, tener acceso aprobado a Creators API y sus credenciales vigentes (Credential ID, Secret y Version). Amazon indica como requisito de acceso actual al menos 10 ventas calificadas en los últimos 30 días. `AMAZON_PARTNER_TAG` debe ser el tracking/store ID del mismo marketplace de `AMAZON_MARKETPLACE`; la credencial-version debe copiarse exactamente desde Associates Central, no adivinarse. Referencias: [requisitos e introducción](https://affiliate-program.amazon.com/creatorsapi/docs/en-us/introduction), [registro/credenciales](https://affiliate-program.amazon.com/creatorsapi/docs/en-us/onboarding/register-for-creators-api), [SearchItems y filtros Prime/ahorro](https://affiliate-program.amazon.com/creatorsapi/docs/en-us/api-reference/operations/search-items), [marketplace y Partner Tag](https://affiliate-program.amazon.com/creatorsapi/docs/en-us/concepts/common-request-headers-and-parameters).

### Diagnóstico de Mercado Libre 403

En la aplicación de Mercado Libre, conserva la redirect URI exacta `https://gracious-renewal-production-76df.up.railway.app/api/v1/meli/oauth/callback`; corrige la URL de notificaciones a `https://central-production-c644.up.railway.app/api/v1/meli/notifications` (sin `z` final). Mantén habilitado OAuth Authorization Code y el acceso de usuario requerido. Para el Worker y Telegram, verifica que `DATABASE_URL` y `MELI_TOKEN_ENCRYPTION_KEY` correspondan a la misma base y clave que usa el callback OAuth.

No agregues scopes de publicaciones, mensajes, ventas o pagos para intentar quitar el 403 de lectura: son permisos distintos y no arreglan por sí solos el endpoint de catálogo. Después de reconectar, con el mismo token y sin compartirlo, prueba `GET https://api.mercadolibre.com/users/me` y luego `GET https://api.mercadolibre.com/sites/MCO/search?q=audifonos%20bluetooth&limit=1`. Si `/users/me` responde 200 pero la búsqueda sigue devolviendo 403, comparte con soporte/desarrolladores de Mercado Libre el `x-request-id`, hora UTC, aplicación/client ID y ruta del recurso; pide que confirmen si la aplicación tiene habilitado acceso a búsqueda de publicaciones (`/sites/MCO/search`). No publiques el access token. El 403 observado desde Railway no se corrige cambiando scopes al azar ni se resuelve desde el código si Mercado Libre deniega el recurso.

---

## Verificación rápida

| Prueba | Resultado esperado |
|--------|--------------------|
| `/help` en @CentralApp_bot | Menú de comandos |
| Logs del bot | `Bot interactivo iniciado` |
| `/estado` | Conteos de productos activos/modelados |
| URL de producto en el chat | Producto capturado + ID |
| `/publicar ID` | Tarjeta publicada |
| `/tienda` en Vercel | Tarjetas visibles |

Con `CATALOG_AUTO_SYNC_ENABLED=false` (predeterminado), el Worker registra `catalog_auto_sync_disabled` y no busca productos externamente. `/estado` solo consulta PostgreSQL; no inicia una búsqueda. `/buscar término` consulta solo los productos persistidos en Central. `/inyectar` solicita explícitamente una ingesta en segundo plano de hasta 200 ofertas por ciclo. Solo se importan y publican productos con imagen/enlace reales, precio actual y precio original verificables, descuento mínimo del 40% y vigencia de 7 días. Los lotes pueden tener menos de 200 productos. `/top` y `/productos` muestran los datos ya guardados. Si Mercado Libre devuelve `403` o `429`, revisar permisos OAuth y esperar el límite antes de reintentar. Amazon requiere Creators API/Partner Tag para verificar precio actual y de referencia; la elegibilidad Prime no se infiere. AliExpress se mantiene en importación por URL hasta tener API afiliada autorizada que entregue ambos precios. TikTok Shop también se incorpora mediante URL. Para volver a la ejecución programada, habilitar `CATALOG_AUTO_SYNC_ENABLED=true`.

---

## Notas importantes

- **Telegram es auxiliar.** La API, el worker y la tienda deben funcionar aunque el bot esté caído.
- Solo **una** instancia debe hacer polling (`getUpdates`). Si hay 409, revisar réplicas o otro servicio con el mismo token.
- No guardar tokens en el repositorio ni en capturas. Regenerar si se filtran.
- No borrar ni recrear la base de producción para “corregir” el catálogo.
- Documentación operativa adicional: [`OPERACION_Y_CONTINUIDAD.md`](OPERACION_Y_CONTINUIDAD.md).

---

## Cuando no haya presupuesto

- Mantener el frontend en Vercel (gratis).
- Dejar el código y esta guía listos.
- No hacer redeploys que dependan de Railway hasta activar el plan.
- Investigar productos y guardar URLs para importar en bloque el día del despliegue.
