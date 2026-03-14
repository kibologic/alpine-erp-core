from datetime import datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class CategoryBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)


class CategoryCreate(CategoryBase):
    pass


class CategoryUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)


class SalesSummaryResponse(BaseModel):
    total_sales_count: int
    total_revenue: Decimal
    total_tax: Decimal
    total_discount: Decimal
    net_revenue: Decimal


class CustomerCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    phone: Optional[str] = Field(None, max_length=50)
    email: Optional[str] = Field(None, max_length=255)


class CustomerResponse(BaseModel):
    id: str
    name: str
    phone: Optional[str]
    email: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


class TopProductResponse(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    sku: str = Field(..., min_length=1, max_length=100)
    barcode: Optional[str] = Field(None, max_length=100)
    category_id: Optional[str] = None
    price: Decimal = Field(default=Decimal("0.0"), ge=0)


class CategoryResponse(CategoryBase):
    id: str
    tenant_id: str
    created_at: datetime

    class Config:
        from_attributes = True


class ProductBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    sku: str = Field(..., min_length=1, max_length=100)
    barcode: Optional[str] = Field(None, max_length=100)
    category_id: Optional[str] = None
    price: Decimal = Field(default=Decimal("0.0"), ge=0)
    cost: Decimal = Field(default=Decimal("0.0"), ge=0)
    tax_rate: Decimal = Field(default=Decimal("0.0"), ge=0, le=100)
    is_active: bool = True


class ProductCreate(ProductBase):
    pass


class ProductUpdate(BaseModel):
    name: Optional[str] = None
    sku: Optional[str] = None
    barcode: Optional[str] = None
    category_id: Optional[str] = None
    price: Optional[Decimal] = Field(None, ge=0)
    cost: Optional[Decimal] = Field(None, ge=0)
    tax_rate: Optional[Decimal] = Field(None, ge=0, le=100)
    is_active: Optional[bool] = None


class ProductResponse(ProductBase):
    id: str
    tenant_id: str
    created_at: datetime
    stock_quantity: Decimal = Decimal("0.0")

    class Config:
        from_attributes = True


class StockAdjustmentCreate(BaseModel):
    product_id: str
    quantity: Decimal = Field(..., description="Positive for addition, negative for deduction")
    reason: str = Field(..., min_length=1, max_length=100)


class StockMovementResponse(BaseModel):
    id: str
    product_id: str
    quantity: Decimal
    reason: str
    reference_type: Optional[str] = None
    reference_id: Optional[str] = None
    created_by: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class InventoryValuationResponse(BaseModel):
    total_items: int
    total_value: Decimal
    currency: str = "MWK"
