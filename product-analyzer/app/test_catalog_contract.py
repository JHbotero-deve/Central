import unittest
from unittest.mock import patch

from catalog_rules import discount_percentage
from amazon_api import _previous_offer
from ingest import fetch_mercadolibre


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


if __name__ == "__main__":
    unittest.main()
