from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.db import SessionLocal, Product

router = APIRouter(prefix="/admin", tags=["Admin"])

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.get("/products")
def list_admin_products(db: Session = Depends(get_db)):
    return db.query(Product).all()

@router.put("/products/{product_id}")
def update_product(product_id: int, data: dict, db: Session = Depends(get_db)):
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Producto no encontrado")
    for key, value in data.items():
        setattr(product, key, value)
    db.commit()
    return {"status": "success", "message": "Tarjeta actualizada"}

@router.delete("/products/{product_id}")
def delete_product(product_id: int, db: Session = Depends(get_db)):
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Producto no encontrado")
    db.delete(product)
    db.commit()
    return {"status": "success", "message": "Tarjeta eliminada"}
