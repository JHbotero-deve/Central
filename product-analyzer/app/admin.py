from fastapi import APIRouter, HTTPException
from app.db import products_collection
from bson import ObjectId

router = APIRouter(prefix="/admin", tags=["Admin"])

@router.get("/products")
def list_admin_products():
    products = list(products_collection.find({}, {"_id": 0}))
    return products

@router.put("/products/{external_id}")
def update_product(external_id: str, data: dict):
    result = products_collection.update_one({"external_id": external_id}, {"$set": data})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Producto no encontrado")
    return {"status": "success", "message": "Tarjeta corregida"}

@router.delete("/products/{external_id}")
def delete_product(external_id: str):
    result = products_collection.delete_one({"external_id": external_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Producto no encontrado")
    return {"status": "success", "message": "Tarjeta eliminada"}
