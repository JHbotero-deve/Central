# Central: documentación operativa y continuidad del proyecto

## Fuente de verdad
- Repositorio: `JHbotero-deve/Central`.
- Frontend público: `product-analyzer/frontend/`; páginas clave: `tienda.html`, `producto.html`, `catalogo.html`, `tarjetas.html`.
- API, ingesta y bot: `product-analyzer/app/`.
- Persistencia de producción: PostgreSQL en Railway. No borrar ni recrear la base de datos para corregir el catálogo.
- CI: `.github/workflows/ci.yml`; auditorías: `scripts/audit_*.py` y `scripts/visualizador_codigo.py --check`.

## Recorrido de un producto
1. Una fuente autorizada o una URL importada entrega datos reales.
2. La ingesta normaliza producto, tienda/origen, URL real, precio e imágenes y los persiste.
3. La publicación determina si la tarjeta está visible.
4. `tienda.html` consulta publicaciones en `/api/v1/publications`, guarda una caché local y dibuja tarjetas.
5. `producto.html` consulta la ficha por ID; utiliza `image_gallery` y la URL de origen para la galería y el enlace de compra.

**No tratar producto, galería y ficha como registros separados.** Las imágenes pertenecen al mismo producto. Conservar `image_gallery` completa, `image_url` principal, descripción y metadatos de tienda/origen, identificador externo, `product_url` y `affiliate_url`. No limitar la persistencia de la galería al número de miniaturas visibles en pantalla.

## Contrato de imágenes y tarjetas
- Mostrar una tarjeta si cumple los requisitos de publicación reales; no exigir datos secundarios que no son necesarios para dibujarla.
- La imagen principal y la galería deben proceder del registro del producto. No crear tarjetas huérfanas para imágenes.
- En la ficha, la galería debe poder navegar todas las imágenes recibidas; el límite visual de miniaturas no debe truncar ni borrar el dato persistido.
- Si el proxy de imágenes falla, intentar la URL original antes de declarar que la imagen no existe.
- Un fallo de imagen debe afectar esa imagen, no ocultar la tarjeta ni el resto del catálogo.
- La acción comercial debe usar `affiliate_url` cuando exista; en caso contrario, `product_url`. Mantener parámetros de seguimiento.
- No inventar productos, precios, descuentos, valoraciones ni enlaces. La tolerancia a datos incompletos significa mostrar lo disponible, no falsificar información.

## Errores y recuperación
- Un 403 de Mercado Libre indica rechazo de un recurso o permisos/token; no significa que el catálogo guardado deba ocultarse ni que otras fuentes deban detenerse.
- Si una fuente falla, registrar fuente, consulta, código HTTP y causa; continuar con las fuentes independientes y conservar productos ya guardados.
- No declarar que Amazon, TikTok o AliExpress importan correctamente sin verificar credenciales, permiso y respuesta real.
- Los productos caducados, publicados y borradores deben distinguirse según el contrato de la API; no despublicar en masa como efecto secundario de un fallo temporal.

## Telegram: servicio auxiliar, no dependencia de la tienda
- Telegram sirve para consultas y alertas; la tienda, la API y el Worker de catálogo deben arrancar y funcionar sin Telegram.
- El aviso de sondeo ocupado puede indicar que otra instancia tiene el bloqueo PostgreSQL. Verificar instancias y bloqueo antes de reiniciar o sustituir el bot.
- No eliminar el bot, sus tokens ni sus datos como primer recurso. Si se decide sustituirlo, hacerlo como cambio aislado, conservando credenciales y capacidad de reversión.
- Un conflicto de Telegram nunca debe abortar ingesta, publicación, lectura de productos ni renderizado del frontend.

## Cómo revisar antes de modificar
1. Leer este documento y los README de raíz y `product-analyzer/`.
2. Revisar rama, commits recientes, estado de CI y diff antes de tocar código.
3. Seguir el producto de extremo a extremo: fuente/URL → ingesta → PostgreSQL → endpoint de publicaciones/producto → tarjeta → ficha/galería → URL comercial.
4. Ejecutar las auditorías de CI y pruebas pertinentes. Las pruebas con credenciales reales deben identificarse por separado.
5. Trabajar en rama propia, commits en español, no reescribir historial ni hacer force push.
6. Desplegar solo tras validar el diff y comprobar el entorno desplegado.

## Estado de cambios y despliegues
Un commit en una rama no implica que esté integrado ni desplegado. Registrar siempre SHA, rama, PR, CI y estado del despliegue por separado. No afirmar que producción está corregida hasta comprobar la URL desplegada.
