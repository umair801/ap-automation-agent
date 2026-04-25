# api/order_router.py

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from typing import Optional

from agents.order_extraction_agent import extract_order_from_text
from core.models import OrderSource
from core.logger import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/orders", tags=["Order Processing"])
templates = Jinja2Templates(directory="templates")


class OrderSubmitRequest(BaseModel):
    text: str
    language_hint: Optional[str] = None


class OrderLineItemResponse(BaseModel):
    line_number: int
    sku: Optional[str]
    description: str
    quantity: str
    unit_of_measure: Optional[str]
    unit_price: Optional[str]
    total: Optional[str]
    delivery_date: Optional[str]


class OrderExtractResponse(BaseModel):
    success: bool
    order_number: Optional[str]
    order_date: Optional[str]
    customer_name: Optional[str]
    customer_email: Optional[str]
    contact_person: Optional[str]
    detected_language: str
    currency: str
    subtotal: Optional[str]
    tax: Optional[str]
    total: Optional[str]
    payment_terms: Optional[str]
    requested_delivery: Optional[str]
    shipping_address: Optional[str]
    confidence: float
    confidence_pct: int
    passed_threshold: bool
    needs_review: bool
    review_reasons: list[str]
    line_items: list[OrderLineItemResponse]
    status: str
    error: Optional[str] = None


@router.get("/demo", response_class=HTMLResponse)
async def order_demo_page(request: Request):
    """Serve the order extraction demo UI."""
    return templates.TemplateResponse("order_demo.html", {"request": request})


@router.post("/extract", response_model=OrderExtractResponse)
async def extract_order(payload: OrderSubmitRequest):
    """
    Extract structured order data from submitted text.
    Supports English and French. Returns confidence score and line items.
    """
    if not payload.text.strip():
        return OrderExtractResponse(
            success=False,
            order_number=None, order_date=None, customer_name=None,
            customer_email=None, contact_person=None,
            detected_language="unknown", currency="USD",
            subtotal=None, tax=None, total=None,
            payment_terms=None, requested_delivery=None, shipping_address=None,
            confidence=0.0, confidence_pct=0, passed_threshold=False,
            needs_review=False, review_reasons=[],
            line_items=[], status="failed",
            error="No text submitted.",
        )

    result = extract_order_from_text(
        text=payload.text,
        source=OrderSource.EMAIL,
    )

    o = result.order

    line_items = [
        OrderLineItemResponse(
            line_number=item.line_number,
            sku=item.sku,
            description=item.description,
            quantity=str(item.quantity),
            unit_of_measure=item.unit_of_measure,
            unit_price=str(item.unit_price) if item.unit_price else None,
            total=str(item.total) if item.total else None,
            delivery_date=str(item.delivery_date) if item.delivery_date else None,
        )
        for item in o.line_items
    ]

    confidence = o.extraction_confidence or 0.0

    return OrderExtractResponse(
        success=result.error is None,
        order_number=o.order_number,
        order_date=str(o.order_date) if o.order_date else None,
        customer_name=o.customer.customer_name if o.customer else None,
        customer_email=o.customer.customer_email if o.customer else None,
        contact_person=o.customer.contact_person if o.customer else None,
        detected_language=o.detected_language.value if o.detected_language else "unknown",
        currency=o.currency,
        subtotal=str(o.subtotal) if o.subtotal else None,
        tax=str(o.tax) if o.tax else None,
        total=str(o.total) if o.total else None,
        payment_terms=o.payment_terms,
        requested_delivery=str(o.requested_delivery) if o.requested_delivery else None,
        shipping_address=o.shipping_address,
        confidence=confidence,
        confidence_pct=int(confidence * 100),
        passed_threshold=not result.needs_review,
        needs_review=result.needs_review,
        review_reasons=o.review_reasons or [],
        line_items=line_items,
        status=o.status.value,
        error=result.error,
    )
