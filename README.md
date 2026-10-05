# Central

Central es el sistema de gestión de oportunidades y catálogo de productos reales. Recibe productos desde las fuentes habilitadas, los persiste en PostgreSQL de Railway, calcula su oportunidad y permite seleccionar manualmente qué productos se publican en la tienda.

## Arquitectura

- Vercel: interfaz web pública y panel Central.
- Railway: API, worker y bot de Telegram.
- PostgreSQL de Railway: catálogo, publicaciones, pedidos y métricas.
- Amazon, Mercado Libre y TikTok Shop: fuentes comerciales según las credenciales disponibles.
- Wompi: pagos de productos propios.

## Rutas públicas

- /: panel Central.
- /tienda: tienda pública.
- /producto/{slug}: ficha de producto publicado.
- /robots.txt: robots del sitio.
- /sitemap.xml: mapa del sitio.
- /api/*: API de Central a través de Railway.

## Operación

El worker ejecuta la ingesta al iniciar y cada 2 horas. Los productos activos caducan a las 48 horas y se renuevan cuando vuelven a detectarse. La publicación en tienda es manual: Central determina qué tarjeta queda visible.

## Tarjetas

Cada producto publicado usa una única tarjeta con imagen real, información en español, precio mostrado en COP y acceso a su ficha o destino comercial. La vista 3D se integra en la tarjeta cuando existe un modelo válido.

## Datos

No se cargan productos de demostración ni catálogos de respaldo. Si una fuente no entrega productos válidos, Central informa la indisponibilidad sin inventar datos.

## Configuración

Las credenciales y secretos se gestionan mediante variables de entorno de Railway y Vercel. La base de datos de producción es PostgreSQL de Railway.
