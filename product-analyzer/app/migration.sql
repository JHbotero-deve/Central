DROP VIEW IF EXISTS product_price_comparison;

CREATE VIEW product_price_comparison AS
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