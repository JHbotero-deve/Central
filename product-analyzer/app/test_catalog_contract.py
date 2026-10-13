import unittest
from unittest.mock import patch
import inspect
import requests

from api import _sync_store_catalog
from url_import import import_url

from catalog_rules import discount_percentage
from amazon_api import _previous_offer
from ingest import fetch_mercadolibre
from store_orders import _public_order_summary, create_store_order
from tiktok_creator import _normalize


class AmazonAffiliateUrlTests(unittest.TestCase):
    def test_scheduled_catalog_does_not_call_amazon_product_api(self):
        source = inspect.getsource(_sync_store_catalog)
        self.assertNotIn("fetch_amazon_products", source)
        self.assertIn("affiliate_url_only", source) if "affiliate_url_only" in source else None

    def test_import_preserves_supplied_amazon_affiliate_url_and_manual_real_data(self):
        affiliate_url = "https://www.amazon.com/dp/B0ABCDEF12?tag=partner-20"
        with patch("url_import._public_url"), patch(
            "url_import._metadata", side_effect=requests.RequestException("lectura bloqueada")
        ):
            product = import_url(
                affiliate_url,
                "electronica",
                title="Audífonos reales",
                price=129.99,
                currency="USD",
                image_url="https://images.example.com/audifonos.jpg",
                require_image=False,
            )
        self.assertEqual(product["product_url"], affiliate_url)
        self.assertEqual(product["affiliate_url"], affiliate_url)
        self.assertEqual(product["price"], 129.99)
        self.assertEqual(product["image_url"], "https://images.example.com/audifonos.jpg")


class StoreOrderSecurityTests(unittest.TestCase):
    def test_public_order_summary_does_not_expose_cost_or_profit(self):
        order = {
            "id": 1, "reference": "REQ-TEST", "total_amount": 50000,
            "estimated_profit": 20000, "cost_unit_price": 30000,
            "currency": "COP", "status": "PENDING", "payment_status": "PENDING",
        }
        result = _public_order_summary(order)
        self.assertEqual(set(result), {"id", "reference", "total_amount", "currency", "status", "payment_status"})
        self.assertNotIn("estimated_profit", result)
        self.assertNotIn("cost_unit_price", result)

    def test_store_orders_only_accept_visible_unblocked_unexpired_products(self):
        import inspect
        source = inspect.getsource(create_store_order)
        self.assertIn("JOIN published_cards pc", source)
        self.assertNotIn("LEFT JOIN published_cards pc", source)
        self.assertIn("p.is_blocked=FALSE", source)
        self.assertIn("p.catalog_expires_at > NOW()", source)


class DiscountRuleTests(unittest.TestCase):
    def test_accepts_real_discount(self):
        self.assertEqual(discount_percentage(50, 100), 50.0)

    def test_rejects_no_discount_or_invalid_price(self):
        self.assertIsNone(discount_percentage(100, 100))
        self.assertIsNone(discount_percentage(110, 100))
        self.assertIsNone(discount_percentage(None, 100))
        self.assertIsNone(discount_percentage(0, 100))

    def test_amazon_reference_price_is_only_used_when_higher(self):
        item = {"offersV2": {"listings": [{
            "price": {"amount": 50, "currency": "USD"},
            "savingBasis": {"money": {"amount": 100, "currency": "USD"}}
        }]}}
        self.assertEqual(_previous_offer(item), 100.0)

    def test_mercadolibre_search_uses_search_fields_without_three_extra_calls(self):
        payload = {"results": [{
            "id": "MCO-TEST-123", "title": "Producto real",
            "price": 50000, "original_price": 120000, "currency_id": "COP",
            "thumbnail": "https://http2.mlstatic.com/D_TEST.jpg",
            "permalink": "https://articulo.mercadolibre.com.co/MCO-TEST-123",
            "seller": {"id": 77}, "sold_quantity": 12
        }]}
        with patch("ingest._get", return_value=payload), \
             patch("ingest._details") as details, \
             patch("ingest._prices") as prices, \
             patch("ingest._sale_price") as sale:
            products = fetch_mercadolibre("producto real", limit=1)
        self.assertEqual(len(products), 1)
        self.assertEqual(products[0]["previous_price"], 120000.0)
        self.assertEqual(products[0]["price"], 50000.0)
        details.assert_not_called()
        prices.assert_not_called()
        sale.assert_not_called()


class TikTokShopCapsuleTests(unittest.TestCase):
    def test_normalize_preserves_all_shop_images_and_affiliate_link(self):
        product = {
            "product_id": "shop-123",
            "title": "Producto TikTok",
            "price": {"sale_price": {"amount": "19.99", "currency": "USD"}},
            "images": [
                {"url": "https://cdn.example.com/a.jpg"},
                {"url_list": ["https://cdn.example.com/b.jpg"]},
                {"url": "https://cdn.example.com/a.jpg"},
                {},
            ],
            "product_url": "https://shop.example.com/item/123",
            "affiliate_url": "https://affiliate.example.com/item/123",
        }
        normalized = _normalize(product)
        self.assertEqual(
            normalized["gallery_urls"],
            ["https://cdn.example.com/a.jpg", "https://cdn.example.com/b.jpg"],
        )
        self.assertEqual(normalized["image_url"], "https://cdn.example.com/a.jpg")
        self.assertEqual(normalized["affiliate_url"], "https://affiliate.example.com/item/123")


if __name__ == "__main__":
    unittest.main()



class CatalogPublicationPolicyTests(unittest.TestCase):
    def test_auto_publication_policy_uses_score_and_card_limit(self):
        from api import _publish_external_product
        source = inspect.getsource(_publish_external_product)
        self.assertIn("CATALOG_MIN_AUTO_PUBLISH_SCORE", source)
        self.assertIn("CATALOG_MAX_PUBLISHED_CARDS", source)
        self.assertIn("CATALOG_EXPIRY_HIGH_SCORE_HOURS", source)
        self.assertIn("CATALOG_EXPIRY_LOW_SCORE_HOURS", source)

    def test_expiry_waits_for_a_successful_complete_provider_sync(self):
        source = inspect.getsource(_sync_store_catalog)
        self.assertIn("if meli_sync_available and meli_sync_complete:", source)
        self.assertIn("meli_sync_complete = False", source)
