from datetime import datetime
from decimal import Decimal
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class SessionOpen(BaseModel):
    register_id: str
    opening_float: Decimal = Field(default=Decimal("0.0"), ge=0)


class SessionClose(BaseModel):
    closing_amount: Decimal = Field(..., ge=0)


class SessionResponse(BaseModel):
    id: str
    register_id: str
    opened_by: str
    opening_float: Decimal
    closed_by: Optional[str] = None
    closing_amount: Optional[Decimal] = None
    discrepancy: Optional[Decimal] = None
    status: str
    opened_at: datetime
    closed_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class SaleLineCreate(BaseModel):
    product_id: str
    quantity: Decimal = Field(..., gt=0)
    unit_price: Decimal = Field(..., ge=0)
    discount: Decimal = Field(default=Decimal("0.0"), ge=0)
    tax: Decimal = Field(default=Decimal("0.0"), ge=0)
    line_total: Decimal = Field(..., ge=0)


class PaymentCreate(BaseModel):
    method: str = Field(..., pattern="^(cash|card)$")
    amount: Decimal = Field(..., gt=0)


class SaleCreate(BaseModel):
    customer_id: Optional[str] = None
    session_id: str
    subtotal: Decimal = Field(..., ge=0)
    tax: Decimal = Field(..., ge=0)
    discount: Decimal = Field(default=Decimal("0.0"), ge=0)
    total: Decimal = Field(..., ge=0)
    lines: List[SaleLineCreate]
    payments: List[PaymentCreate]


class SaleLineResponse(BaseModel):
    id: str
    product_id: str
    quantity: Decimal
    unit_price: Decimal
    line_total: Decimal

    class Config:
        from_attributes = True


class PaymentResponse(BaseModel):
    id: str
    method: str
    amount: Decimal
    created_at: datetime

    class Config:
        from_attributes = True


class SaleResponse(BaseModel):
    id: str
    sale_number: str
    customer_id: Optional[str] = None
    cashier_id: str
    session_id: str
    subtotal: Decimal
    tax: Decimal
    discount: Decimal
    total: Decimal
    status: str
    created_at: datetime
    lines: List[SaleLineResponse]
    payments: List[PaymentResponse]

    class Config:
        from_attributes = True
