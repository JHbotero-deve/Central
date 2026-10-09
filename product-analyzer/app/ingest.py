from datetime import datetime, timedelta
from app.db import products_collection

def purge_expired_products():
    threshold = datetime.utcnow() - timedelta(hours=48)
    products_collection.delete_many({"created_at": {"$lt": threshold}})

def safe_ingest_product(product_data):
    try:
        purge_expired_products()
        discount = product_data.get("discount_percentage", 0.0)
        if discount < 50.0:
            return False
            
        external_id = product_data.get("external_id")
        platform = product_data.get("platform", "aliexpress").lower()
        
        if not external_id or platform not in ["aliexpress", "mercadolibre", "amazon"]:
            return False
            
        product_data["created_at"] = datetime.utcnow()
        
        products_collection.update_one(
            {"external_id": external_id, "platform": platform},
            {"$set": product_data},
            upsert=True
        )
        return True
    except Exception:
        return False
