# agents/order_extraction_agent.py

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Optional

from openai import OpenAI

from core.config import get_settings
from core.logger import get_logger
from core.models import (
    SalesOrder,
    OrderStatus,
    OrderSource,
    OrderLanguage,
    OrderLineItem,
    CustomerInfo,
    OrderReviewItem,
)

logger = get_logger(__name__)
settings = get_settings()
client = OpenAI(api_key=settings.openai_api_key)

# Extractions below this score go to the human review queue.
ORDER_CONFIDENCE_THRESHOLD = 0.70

# --- Prompts ------------------------------------------------------------------

ORDER_EXTRACTION_PROMPT = """\
You are a specialist in extracting structured sales order data from business documents.
The document may be written in English or French. Extract all fields regardless of language.

Return a single valid JSON object only. No explanation. No markdown. No code fences.

{
  "detected_language": "en" or "fr" or "unknown",
  "order_number": "string or null",
  "order_date": "YYYY-MM-DD or null",
  "requested_delivery": "YYYY-MM-DD or null",
  "customer_po_ref": "buyer PO reference number or null",
  "currency": "3-letter ISO code, default USD",
  "subtotal": "numeric string or null",
  "tax": "numeric string or null",
  "total": "numeric string or null",
  "payment_terms": "string or null",
  "shipping_address": "full address string or null",
  "billing_address": "full address string or null",
  "notes": "any additional notes or special instructions or null",
  "customer": {
    "customer_name": "string or null",
    "customer_id": "account or customer code or null",
    "customer_email": "string or null",
    "customer_phone": "string or null",
    "customer_address": "string or null",
    "contact_person": "name of the contact person or null"
  },
  "line_items": [
    {
      "line_number": integer,
      "sku": "product code or SKU or null",
      "description": "product description",
      "quantity": "numeric string",
      "unit_of_measure": "e.g. each, box, kg or null",
      "unit_price": "numeric string or null",
      "total": "numeric string or null",
      "delivery_date": "YYYY-MM-DD or null",
      "customer_line_ref": "buyer line reference or null"
    }
  ],
  "confidence": float between 0.0 and 1.0,
  "low_confidence_reasons": ["list of strings explaining any uncertainty, or empty list"]
}

Rules:
- Monetary values: plain numeric strings, no currency symbols or commas. Example: "1250.00"
- Dates: YYYY-MM-DD format only
- quantity must be a numeric string even if it appears as an integer
- If customer block has no data at all, return null for the customer field
- confidence reflects completeness: 1.0 = all key fields present and clear
- Key fields for confidence: order_number, order_date, customer.customer_name, line_items with SKU and quantity
- Return only the JSON object. Nothing else.
"""

# --- Helpers ------------------------------------------------------------------

def _safe_decimal(value: Optional[str]) -> Optional[Decimal]:
    if value is None:
        return None
    try:
        return Decimal(str(value).replace(",", "").replace("$", "").strip())
    except InvalidOperation:
        return None


def _parse_date(value: Optional[str]) -> Optional[date]:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except (ValueError, TypeError):
        return None


def _parse_language(value: Optional[str]) -> OrderLanguage:
    mapping = {"en": OrderLanguage.ENGLISH, "fr": OrderLanguage.FRENCH}
    return mapping.get(str(value).lower(), OrderLanguage.UNKNOWN)


def _build_order_line_items(raw: list) -> list[OrderLineItem]:
    items = []
    for i, row in enumerate(raw):
        try:
            items.append(OrderLineItem(
                line_number=int(row.get("line_number", i + 1)),
                sku=row.get("sku"),
                description=str(row.get("description", "")).strip(),
                quantity=_safe_decimal(row.get("quantity", "1")) or Decimal("1"),
                unit_price=_safe_decimal(row.get("unit_price")),
                total=_safe_decimal(row.get("total")),
                unit_of_measure=row.get("unit_of_measure"),
                delivery_date=_parse_date(row.get("delivery_date")),
                customer_line_ref=row.get("customer_line_ref"),
            ))
        except Exception as e:
            logger.warning("Failed to parse order line item", index=i, error=str(e))
    return items


def _build_customer(raw: Optional[dict]) -> Optional[CustomerInfo]:
    if not raw:
        return None
    name = raw.get("customer_name")
    if not name:
        return None
    return CustomerInfo(
        customer_name=name,
        customer_id=raw.get("customer_id"),
        customer_email=raw.get("customer_email"),
        customer_phone=raw.get("customer_phone"),
        customer_address=raw.get("customer_address"),
        contact_person=raw.get("contact_person"),
    )


# --- Result dataclass ---------------------------------------------------------

@dataclass
class OrderExtractionResult:
    order: SalesOrder
    review_item: Optional[OrderReviewItem]   # set when confidence < threshold
    needs_review: bool
    error: Optional[str] = None


# --- Core parser --------------------------------------------------------------

def _parse_gpt_response(raw_json: str, order: SalesOrder, raw_text: str) -> OrderExtractionResult:
    """Parse GPT-4o JSON into a SalesOrder. Route to review queue if needed."""
    try:
        data = json.loads(raw_json.strip())
    except json.JSONDecodeError as e:
        logger.error("GPT-4o returned invalid JSON", error=str(e))
        order.status = OrderStatus.FAILED
        return OrderExtractionResult(order=order, review_item=None, needs_review=False, error=str(e))

    order.detected_language  = _parse_language(data.get("detected_language"))
    order.order_number       = data.get("order_number")
    order.order_date         = _parse_date(data.get("order_date"))
    order.requested_delivery = _parse_date(data.get("requested_delivery"))
    order.customer_po_ref    = data.get("customer_po_ref")
    order.currency           = data.get("currency") or "USD"
    order.subtotal           = _safe_decimal(data.get("subtotal"))
    order.tax                = _safe_decimal(data.get("tax"))
    order.total              = _safe_decimal(data.get("total"))
    order.payment_terms      = data.get("payment_terms")
    order.shipping_address   = data.get("shipping_address")
    order.billing_address    = data.get("billing_address")
    order.notes              = data.get("notes")
    order.customer           = _build_customer(data.get("customer"))
    order.line_items         = _build_order_line_items(data.get("line_items") or [])
    order.extraction_confidence = float(data.get("confidence") or 0.0)
    order.status             = OrderStatus.EXTRACTED

    low_confidence_reasons: list[str] = data.get("low_confidence_reasons") or []

    needs_review = order.extraction_confidence < ORDER_CONFIDENCE_THRESHOLD
    review_item: Optional[OrderReviewItem] = None

    if needs_review:
        order.status = OrderStatus.REVIEW_NEEDED
        order.review_reasons = low_confidence_reasons
        review_item = OrderReviewItem(
            order_id=order.id,
            confidence=order.extraction_confidence,
            reasons=low_confidence_reasons,
            raw_text=raw_text[:4000],
        )
        logger.warning(
            "Order routed to human review",
            order_id=str(order.id),
            confidence=order.extraction_confidence,
            reasons=low_confidence_reasons,
        )
    else:
        logger.info(
            "Order extraction passed threshold",
            order_id=str(order.id),
            confidence=order.extraction_confidence,
            language=order.detected_language,
            line_items=len(order.line_items),
        )

    return OrderExtractionResult(order=order, review_item=review_item, needs_review=needs_review)


# --- Public API ---------------------------------------------------------------

def extract_order_from_text(
    text: str,
    source: OrderSource = OrderSource.EMAIL,
    email_message_id: Optional[str] = None,
) -> OrderExtractionResult:
    """
    Extract a SalesOrder from plain text (email body or parsed attachment).
    Supports English and French content.

    Args:
        text:             Raw text content of the email or document.
        source:           Ingestion source enum value.
        email_message_id: Optional email message ID for traceability.

    Returns:
        OrderExtractionResult with populated SalesOrder and optional review item.
    """
    order = SalesOrder(
        source=source,
        email_message_id=email_message_id,
        status=OrderStatus.EXTRACTING,
    )

    prompt = ORDER_EXTRACTION_PROMPT + "\n\nDOCUMENT TEXT:\n" + text

    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            max_tokens=3000,
        )
        raw_json = response.choices[0].message.content
        order.extraction_model = "gpt-4o-text"
        return _parse_gpt_response(raw_json, order, text)

    except Exception as e:
        logger.error("Order extraction failed", error=str(e))
        order.status = OrderStatus.FAILED
        return OrderExtractionResult(order=order, review_item=None, needs_review=False, error=str(e))
