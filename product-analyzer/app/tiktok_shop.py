import os
import requests

RAPIDAPI_KEY = os.getenv("RAPIDAPI_KEY")
RAPIDAPI_HOST = os.getenv("RAPIDAPI_HOST")

def fetch_tiktok_trends(keyword):
    if not RAPIDAPI_KEY:
        print("[TikTok] Error: RAPIDAPI_KEY no configurada")
        return []

    url = f"https://{RAPIDAPI_HOST}/search"
    querystring = {"keyword": keyword, "count": "10"}
    
    headers = {
        "X-RapidAPI-Key": RAPIDAPI_KEY,
        "X-RapidAPI-Host": RAPIDAPI_HOST
    }

    try:
        response = requests.get(url, headers=headers, params=querystring, timeout=15)
        response.raise_for_status()
        data = response.json()
        
        trends = []
        # Adaptamos la respuesta genérica de RapidAPI a nuestro formato interno
        for video in data.get("data", []):
            trends.append({
                "title": video.get("desc"),
                "views": video.get("play_count"),
                "likes": video.get("digg_count"),
                "shares": video.get("share_count"),
                "url": video.get("share_url")
            })
        return trends
    except Exception as e:
        print(f"[TikTok Error] {e}")
        return []
