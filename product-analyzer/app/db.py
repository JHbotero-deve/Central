import os
from pymongo import MongoClient

MONGO_URL = os.getenv("MONGO_URL", "mongodb://localhost:27017")
client = MongoClient(MONGO_URL)
db = client["central_products"]
products_collection = db["products"]
products_collection.create_index([("external_id", 1), ("platform", 1)], unique=True)
