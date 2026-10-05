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
