"""Pydantic models used by the customer support business layer."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Customer(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    customer_id: str
    name: str
    email: str
    loyalty_tier: str


class Order(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    order_id: str
    customer_id: str
    amount: float
    status: str
    payment_status: str
    created_at: datetime


class RefundRequest(BaseModel):
    request_id: str = Field(min_length=1)
    customer_id: str
    order_id: str
    amount: float = Field(gt=0)
    reason: str


class RefundResponse(BaseModel):
    request_id: str
    customer_id: str
    order_id: str
    amount: float
    status: Literal["approved", "rejected"]
    message: str


class StoreCreditRequest(BaseModel):
    request_id: str = Field(min_length=1)
    customer_id: str
    amount: float = Field(gt=0)
    reason: str


class StoreCreditResponse(BaseModel):
    request_id: str
    customer_id: str
    amount: float
    status: Literal["issued", "rejected"]
    message: str


class AuditEntry(BaseModel):
    timestamp: datetime
    action: str
    request_id: str
    customer_id: str
    order_id: str | None = None
    amount: float
    status: str
