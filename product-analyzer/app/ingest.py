from datetime import datetime, timedelta
from sqlalchemy.exc import SQLAlchemyError
from app.db import Product

def purge_expired_products(db_session):
    threshold = datetime.utcnow() - timedelta(hours=48)
    db_session.query(Product).filter(Product.created_at < threshold).delete()
    db_session.commit()

def safe_ingest_product(db_session, product_data):
    try:
        purge_expired_products(db_session)
        discount = product_data.get("discount_percentage", 0.0)
        if discount < 50.0:
            return False
        external_id = product_data.get("external_id")
        platform = product_data.get("platform", "aliexpress")
        if not external_id:
            return False
        existing = db_session.query(Product).filter_by(external_id=external_id, platform=platform).first()
        if existing:
            for key, value in product_data.items():
                setattr(existing, key, value)
            existing.created_at = datetime.utcnow()
        else:
            new_product = Product(**product_data)
            db_session.add(new_product)
        db_session.commit()
        return True
    except SQLAlchemyError:
        db_session.rollback()
        return False
