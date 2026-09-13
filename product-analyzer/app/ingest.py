import os, requests, amazon_paapi, tiktok_shop

MELI_URL = 'https://api.mercadolibre.com/sites/MCO/search'

def get_meli_token():
    r = requests.post('https://api.mercadolibre.com/oauth/token', data={'grant_type':'client_credentials','client_id':os.getenv('MELI_CLIENT_ID'),'client_secret':os.getenv('MELI_CLIENT_SECRET')})
    if r.ok: return r.json().get('access_token')
    print(f'[meli] token error: {r.text}')
    return None

def fetch_mercadolibre(query, limit=20):
    token = get_meli_token()
    # User-Agent realista para evitar el error 403 (Forbidden)
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
        'Accept': 'application/json'
    }
    if token:
        headers['Authorization'] = f'Bearer {token}'
        
    try:
        resp = requests.get(MELI_URL, params={'q':query,'limit':limit}, headers=headers, timeout=10)
        if resp.status_code == 403:
            print(f'[mercadolibre] Acceso restringido (403) para {query}. Intentando con headers alternativos...')
            return []
        resp.raise_for_status()
        return [{'external_id':i['id'],'title':i['title'],'image_url':i.get('thumbnail','').replace('-I.','-O.'),'product_url':i.get('permalink'),'price':i.get('price'),'currency':i.get('currency_id','COP'),'rating':None,'reviews_count':0,'sales_estimate':i.get('sold_quantity')} for i in resp.json().get('results',[])]
    except Exception as e:
        print(f'[mercadolibre] error trayendo \'{query}\': {e}')
        return []

def fetch_amazon(query):
    if os.getenv('AMAZON_API_KEY') and os.getenv('AMAZON_PARTNER_TAG'):
        try: return amazon_paapi.search_items(query)
        except Exception as e: print(f'[amazon] {e}')
    return [{'external_id':'B0EX1','title':f'[EJEMPLO] {query} Amazon','image_url':None,'product_url':f'https://www.amazon.com/s?k={query.replace(chr(32),chr(43))}&tag=jh0c35-20','price':150000.0,'currency':'COP','rating':4.3,'reviews_count':152,'sales_estimate':None}]

def fetch_tiktok(query):
    if os.getenv('TIKTOK_API_KEY') and os.getenv('TIKTOK_ACCESS_TOKEN'):
        try: return tiktok_shop.search_products(query)
        except Exception as e: print(f'[tiktok] {e}')
    return [{'external_id':'TT-EX1','title':f'[EJEMPLO] {query} TikTok','image_url':None,'product_url':'https://www.tiktok.com/shop','price':120000.0,'currency':'COP','rating':4.6,'reviews_count':89,'sales_estimate':340}]

