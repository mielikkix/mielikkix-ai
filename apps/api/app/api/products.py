import json
from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..core.database import get_db
from ..core.dependencies import get_current_user, get_current_business
from ..models.user import User
from ..models.business import Business
from ..models.product import Product
from ..schemas.product import ProductCreate, ProductUpdate, ProductOut
from ..services import plan_service
from ..rag.embeddings import embed_query

router = APIRouter(prefix="/api/products", tags=["products"])


def _product_embedding_text(product: Product) -> str:
    return f"{product.name} {product.category or ''} {product.description or ''}".strip()


@router.get("", response_model=List[ProductOut])
def list_products(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return db.query(Product).filter(Product.business_id == current_user.business_id).all()


@router.post("", response_model=ProductOut)
def create_product(
    body: ProductCreate,
    current_user: User = Depends(get_current_user),
    business: Business = Depends(get_current_business),
    db: Session = Depends(get_db),
):
    plan_service.check_product_limit(db, business)
    if body.currency != "USD" and not plan_service.resolve_features(business)["multi_currency"]:
        raise HTTPException(
            status_code=403,
            detail="Your plan only supports USD pricing. Upgrade your plan to use other currencies.",
        )
    product = Product(business_id=current_user.business_id, **body.model_dump())
    product.embedding_json = json.dumps(embed_query(_product_embedding_text(product)))
    db.add(product)
    db.commit()
    db.refresh(product)
    return product


@router.patch("/{product_id}", response_model=ProductOut)
def update_product(
    product_id: str,
    body: ProductUpdate,
    current_user: User = Depends(get_current_user),
    business: Business = Depends(get_current_business),
    db: Session = Depends(get_db),
):
    product = db.query(Product).filter(
        Product.id == product_id, Product.business_id == current_user.business_id
    ).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    updates = body.model_dump(exclude_none=True)
    if "currency" in updates and updates["currency"] != "USD" and not plan_service.resolve_features(business)["multi_currency"]:
        raise HTTPException(
            status_code=403,
            detail="Your plan only supports USD pricing. Upgrade your plan to use other currencies.",
        )
    for field, val in updates.items():
        setattr(product, field, val)
    if {"name", "category", "description"} & updates.keys():
        product.embedding_json = json.dumps(embed_query(_product_embedding_text(product)))
    db.commit()
    db.refresh(product)
    return product


@router.delete("/{product_id}")
def delete_product(
    product_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    product = db.query(Product).filter(
        Product.id == product_id, Product.business_id == current_user.business_id
    ).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    db.delete(product)
    db.commit()
    return {"ok": True}
