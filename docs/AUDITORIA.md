# Auditoría completa de Central

Fecha: 2026-10-13  
Alcance: repositorio `JHbotero-deve/Central`, arquitectura, bot Telegram, despliegue Railway, variables y documentación.

## Resumen ejecutivo

El código de Central está **orientado y mayormente listo**. El bloqueo actual de producción no es de lógica de negocio: el trial de Railway expiró y el servicio `central-telegram` no tiene deployment activo. Además, `telegram_alert.py` no tenía punto de entrada `__main__`, por lo que `python telegram_alert.py` no arrancaba el bot (docker-compose ya usaba `python -c "from telegram_alert import run_bot; run_bot()"`).

## Bloques auditados

### 1. Bot de Telegram (`product-analyzer/app/telegram_alert.py`)

| Hallazgo | Severidad | Acción |
|----------|-----------|--------|
| Sin `if __name__ == "__main__"` | Alta | **Corregido**: se añadió `run_bot()` al ejecutar el módulo |
| Token y Chat ID correctos en diseño | — | OK |
| Bloqueo de polling con PostgreSQL | — | OK |
| Comandos /help, /top, /buscar, /agregar, /publicar, /estado | — | OK |
| Importación por URL en mensaje libre | — | OK |

Start Command recomendado en Railway:
```bash
python telegram_alert.py
```

### 2. API y Worker

| Componente | Estado |
|------------|--------|
| `api.py` | Presente, FastAPI amplio |
| `main.py` (worker) | Loop de catálogo cada 2 h + `/health` |
| Dockerfiles | Arrancan uvicorn (API), no el bot — correcto si el bot es servicio aparte |
| `docker-compose.yml` | Define servicios `api`, `app` (worker), `telegram` — referencia local válida |

### 3. Variables de entorno

| Antes | Después |
|-------|---------|
| `.env.example` incompleto (faltaban `ADMIN_API_KEY`, `PUBLIC_STORE_URL`, `CENTRAL_API_BASE`, `MELI_TOKEN_ENCRYPTION_KEY`, Mongo) | **Actualizado** con secciones por rol y comentarios de seguridad |

### 4. Documentación

| Documento | Estado |
|-----------|--------|
| `docs/OPERACION_Y_CONTINUIDAD.md` | Completo y alineado |
| `docs/DESPLIEGUE.md` | Guía de servicios, variables, checklist del día de pago |
| README raíz | Enlace a DESPLIEGUE y AUDITORIA |
| Esta auditoría | `docs/AUDITORIA.md` |

### 5. Frontend (Vercel)

- Rutas documentadas: `/`, `/tienda`, `/producto/{slug}`
- Depende de la API Railway; con trial expirado la tienda no recibe datos frescos
- Sin cambios de código en esta pasada

### 6. Seguridad

- Token de Telegram se expuso en chat de soporte → **revocar y regenerar** al reactivar Railway
- Secretos no deben ir en Git (`.env.example` solo placeholders)
- Semillas demo protegidas por `CENTRAL_ALLOW_*` — no activar en producción

### 7. Infraestructura Railway (estado operativo)

| Servicio | Estado observado |
|----------|------------------|
| `central-telegram` | Sin deployment — trial expirado |
| API / DB | Dependientes del mismo plan |
| Vercel frontend | Activo (`central-7ykr.vercel.app`) |

## Cambios aplicados en esta auditoría

1. Entrypoint `__main__` en `telegram_alert.py`
2. `.env.example` ampliado y ordenado
3. `docs/DESPLIEGUE.md`
4. `docs/AUDITORIA.md` (este informe)
5. README raíz: enlace a despliegue y auditoría

## Qué NO se tocó (a propósito)

- Lógica de scoring, ingestión, publicaciones y OAuth
- Esquema SQL
- Frontend HTML/CSS/JS
- Credenciales reales (no existen en el repo)

## Checklist post-reactivación

1. Plan Railway activo
2. Token Telegram nuevo en BotFather
3. Servicio bot: variables + Start Command `python telegram_alert.py`
4. Logs: `Bot interactivo iniciado`
5. `/help` responde en @CentralApp_bot
6. Probar import URL + `/publicar ID`

## Conclusión

Central queda **limpio y orientado para despliegue**. Con presupuesto (Hobby ~$5/mes) el checklist de `docs/DESPLIEGUE.md` debe dejar bot, API y tienda operativos en menos de 30 minutos.
