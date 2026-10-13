# Central — Guía de despliegue

Documento operativo para levantar Central cuando haya presupuesto (Railway Hobby u otro plan de pago).

## Arquitectura de servicios

| Servicio Railway | Rol | Start Command recomendado |
|------------------|-----|---------------------------|
| **API** (ej. `gracious-renewal`) | API FastAPI + rutas de publicaciones, OAuth, comercio | `uvicorn api:app --host 0.0.0.0 --port $PORT` |
| **Worker** (opcional, puede ser el mismo que API) | Sincronización de catálogo cada 2 h | `uvicorn main:app --host 0.0.0.0 --port $PORT` o el entrypoint del worker |
| **central-telegram** | Bot de Telegram (polling) | `python telegram_alert.py` |
| **PostgreSQL** | Base de datos | Gestionado por Railway |
| **Vercel** | Frontend público y panel | Automático desde `product-analyzer/frontend` |

> El bot de Telegram **debe** ser un servicio separado (o un proceso dedicado). Los Dockerfiles actuales arrancan solo la API (`uvicorn`). Si el servicio `central-telegram` usa el mismo Dockerfile, sobrescribe el **Start Command** en Railway.

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
| `ALIEXPRESS_APP_KEY` | AliExpress Open Platform |
| `ALIEXPRESS_APP_SECRET` | AliExpress Open Platform |
| `ALIEXPRESS_CALLBACK_URL` | Por defecto: `https://central-7ykr.vercel.app/api/v1/aliexpress/oauth/callback` |
| `ALIEXPRESS_TOKEN_ENCRYPTION_KEY` | Opcional; si falta reutiliza `MELI_TOKEN_ENCRYPTION_KEY` |
| Credenciales Amazon / TikTok / Wompi | Según módulos habilitados |
| `CATALOG_SYNC_INTERVAL_SECONDS` | Intervalo del worker (por defecto 7200) |

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

### Worker de catálogo (si es servicio aparte)
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
