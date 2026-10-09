import os
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure

MONGO_URL = os.getenv("MONGO_URL", "mongodb://localhost:27017")
client = MongoClient(MONGO_URL, serverSelectionTimeoutMS=2000)
db = client["central_products"]
products_collection = db["products"]

def ensure_indexes():
    try:
        products_collection.create_index([("external_id", 1), ("platform", 1)], unique=True)
    except Exception:
        pass

ensure_indexes()
