import os
import requests

RAINFOREST_API_KEY = os.getenv("RAINFOREST_API_KEY")

def fetch_amazon_products(keyword):
    if not RAINFOREST_API_KEY:
        print("[Amazon] Error: RAINFOREST_API_KEY no configurada")
        return []

    params = {
        "api_key": RAINFOREST_API_KEY,
        "amazon_domain": "amazon.com",
        "search_term": keyword
    }
    
    try:
        response = requests.get("https://api.rainforestapi.com/request", params=params, timeout=15)
        response.raise_for_status()
        data = response.json()
        
        products = []
        for item in data.get("search_results", []):
            products.append({
                "title": item.get("title"),
                "price": item.get("price", {}).get("value"),
                "url": item.get("link"),
                "rating": item.get("rating"),
                "reviews": item.get("ratings_total")
            })
        return products
    except Exception as e:
        print(f"[Amazon Error] {e}")
        return []
