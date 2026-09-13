import os
import requests
from bs4 import BeautifulSoup

def search_items(keyword):
    print(f"[Amazon Scraper] Buscando: {keyword}...")
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://www.google.com/"
    }
    
    url = f"https://www.amazon.com/s?k={keyword.replace(' ', '+')}"
    
    try:
        response = requests.get(url, headers=headers, timeout=15)
        if response.status_code == 404:
            print("[Amazon] Producto no encontrado.")
            return []
            
        soup = BeautifulSoup(response.text, "html.parser")
        products = []
        
        for index, item in enumerate(soup.select(".s-result-item[data-component-type='s-search-result']")):
            title_elem = item.select_one("h2 a span")
            price_elem = item.select_one(".a-price-whole")
            link_elem = item.select_one("h2 a")
            
            if title_elem and price_elem:
                clean_price = price_elem.text.replace(',', '').replace('$', '').strip()
                try:
                    final_price = float(clean_price)
                except:
                    final_price = 0.0

                products.append({
                    "external_id": f"AMZ-{index}",
                    "title": title_elem.text.strip(),
                    "price": final_price,
                    "image_url": None,
                    "product_url": "https://www.amazon.com" + link_elem['href'],
                    "currency": "USD",
                    "rating": 0.0, 
                    "reviews_count": 0,
                    "sales_estimate": 0
                })
        
        print(f"[Amazon Scraper] Encontrados {len(products)} productos.")
        return products
    except Exception as e:
        print(f"[Amazon Scraping Error] {e}")
        return []

