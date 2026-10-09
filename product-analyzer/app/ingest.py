from sqlalchemy.exc import SQLAlchemyError
from app.db import Product

def safe_ingest_product(db_session, product_data):
    try:
        external_id = product_data.get("external_id")
        existing = db_session.query(Product).filter_by(external_id=external_id).first()
        if existing:
            for key, value in product_data.items():
                setattr(existing, key, value)
        else:
            new_product = Product(**product_data)
            db_session.add(new_product)
        db_session.commit()
        return True
    except SQLAlchemyError:
        db_session.rollback()
        return False
