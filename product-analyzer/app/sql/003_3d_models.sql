-- =========================================================
-- Soporte de modelado 3D por producto
-- =========================================================

-- URL a un modelo 3D real (.glb/.gltf), opcional. Si está vacío, el frontend
-- genera una vista 3D texturizada a partir de la foto del producto.
ALTER TABLE products ADD COLUMN IF NOT EXISTS model_url TEXT;

-- Forma de referencia para elegir la geometría del visor 3D cuando no hay
-- modelo real: 'garment' (remera/campera), 'footwear' (calzado), 'accessory'
ALTER TABLE products ADD COLUMN IF NOT EXISTS model_shape VARCHAR(20) DEFAULT 'garment';

-- Actualiza la vista de comparación para incluir lo necesario para el visor 3D
CREATE OR REPLACE VIEW product_price_comparison AS
SELECT
    p.id,
    p.title,
    pl.name AS platform,
    p.current_price,
    p.rating,
    p.product_url,
    p.image_url,
    p.model_url,
    p.model_shape
FROM products p
JOIN platforms pl ON pl.id = p.platform_id
WHERE p.is_active = TRUE
ORDER BY p.title, p.current_price ASC;
