# agents/order_erp_sync_agent.py

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

import structlog

from core.models import SalesOrder, OrderStatus, ERPProvider

logger = structlog.get_logger(__name__)

MAX_RETRIES = 3
RETRY_DELAY_SECONDS = 2


# --- Sync result --------------------------------------------------------------

@dataclass
class OrderSyncResult:
    """Result of a single order ERP sync attempt."""
    order_id: str
    order_number: Optional[str]
    erp_provider: str
    success: bool
    erp_transaction_id: Optional[str] = None
    error_message: Optional[str] = None
    attempts: int = 1

    # Audit fields
    source_email_id: Optional[str] = None
    customer_name: Optional[str] = None
    total_value: Optional[str] = None
    line_item_count: int = 0
    synced_at: datetime = field(default_factory=datetime.utcnow)


# --- Field mappers ------------------------------------------------------------

def _map_line_items_generic(order: SalesOrder) -> list[dict[str, Any]]:
    """Produce a generic line item list suitable for any ERP adapter."""
    return [
        {
            "line_number": item.line_number,
            "sku": item.sku,
            "description": item.description,
            "quantity": float(item.quantity),
            "unit_price": float(item.unit_price) if item.unit_price else None,
            "total": float(item.total) if item.total else None,
            "unit_of_measure": item.unit_of_measure,
            "delivery_date": str(item.delivery_date) if item.delivery_date else None,
            "customer_line_ref": item.customer_line_ref,
        }
        for item in order.line_items
    ]


def _map_to_erp_payload(order: SalesOrder, erp_provider: ERPProvider) -> dict[str, Any]:
    """
    Map a SalesOrder to the target ERP's expected payload structure.
    Extend the provider-specific blocks as the client's ERP schema becomes known.
    """
    customer_name = order.customer.customer_name if order.customer else "Unknown"
    line_items = _map_line_items_generic(order)

    base = {
        "order_number": order.order_number,
        "order_date": str(order.order_date) if order.order_date else None,
        "requested_delivery": str(order.requested_delivery) if order.requested_delivery else None,
        "customer_name": customer_name,
        "customer_id": order.customer.customer_id if order.customer else None,
        "customer_po_ref": order.customer_po_ref,
        "currency": order.currency,
        "subtotal": float(order.subtotal) if order.subtotal else None,
        "tax": float(order.tax) if order.tax else None,
        "total": float(order.total) if order.total else None,
        "payment_terms": order.payment_terms,
        "shipping_address": order.shipping_address,
        "billing_address": order.billing_address,
        "notes": order.notes,
        "line_items": line_items,
    }

    if erp_provider == ERPProvider.QUICKBOOKS:
        # QuickBooks SalesReceipt / Estimate structure
        return {
            "CustomerRef": {"name": customer_name},
            "DocNumber": order.order_number,
            "TxnDate": str(order.order_date) if order.order_date else None,
            "CurrencyRef": {"value": order.currency},
            "Line": [
                {
                    "DetailType": "SalesItemLineDetail",
                    "Amount": item["total"] or 0,
                    "SalesItemLineDetail": {
                        "ItemRef": {"name": item["description"]},
                        "Qty": item["quantity"],
                        "UnitPrice": item["unit_price"] or 0,
                    },
                }
                for item in line_items
            ],
            "CustomerMemo": {"value": order.notes or ""},
        }

    if erp_provider == ERPProvider.XERO:
        # Xero Invoice (ACCREC) structure
        return {
            "Type": "ACCREC",
            "Contact": {"Name": customer_name},
            "InvoiceNumber": order.order_number,
            "Date": str(order.order_date) if order.order_date else None,
            "DueDate": str(order.requested_delivery) if order.requested_delivery else None,
            "CurrencyCode": order.currency,
            "LineItems": [
                {
                    "Description": item["description"],
                    "Quantity": item["quantity"],
                    "UnitAmount": item["unit_price"] or 0,
                    "AccountCode": "200",
                }
                for item in line_items
            ],
            "Reference": order.customer_po_ref or "",
        }

    # SAP / NetSuite: return the normalised base payload.
    # Swap in real field mappings when the client's ERP schema is confirmed.
    return base


def _push_to_erp(payload: dict[str, Any], erp_provider: ERPProvider, order_number: Optional[str]) -> str:
    """
    Push the mapped payload to the target ERP.
    Returns an ERP transaction ID string on success.

    Real HTTP calls replace the stubs below once client credentials are provided.
    """
    if erp_provider == ERPProvider.QUICKBOOKS:
        # Replace with: quickbooks_client.create_sales_receipt(payload)
        logger.info("quickbooks_order_push_stub", order_number=order_number)
        return f"QB-ORD-{order_number or 'UNKNOWN'}"

    if erp_provider == ERPProvider.XERO:
        # Replace with: xero_client.create_sales_invoice(payload)
        logger.info("xero_order_push_stub", order_number=order_number)
        return f"XERO-ORD-{order_number or 'UNKNOWN'}"

    if erp_provider == ERPProvider.SAP:
        # Replace with: sap_client.post_sales_order(payload)
        logger.info("sap_order_push_stub", order_number=order_number)
        return f"SAP-ORD-{order_number or 'UNKNOWN'}"

    if erp_provider == ERPProvider.NETSUITE:
        # Replace with: netsuite_client.create_sales_order(payload)
        logger.info("netsuite_order_push_stub", order_number=order_number)
        return f"NS-ORD-{order_number or 'UNKNOWN'}"

    raise ValueError(f"Unsupported ERP provider: {erp_provider}")


# --- Main agent ---------------------------------------------------------------

class OrderERPSyncAgent:
    """
    Maps extracted SalesOrder fields to the target ERP schema and pushes
    the order with retry logic. Logs every attempt with full audit context.
    """

    def __init__(self, erp_provider: ERPProvider) -> None:
        self.erp_provider = erp_provider
        self.log = logger.bind(agent="order_erp_sync_agent", erp=erp_provider.value)

    def sync_order(self, order: SalesOrder) -> OrderSyncResult:
        """
        Sync a validated SalesOrder to the configured ERP.

        Args:
            order: A SalesOrder with status VALIDATED or EXTRACTED.

        Returns:
            OrderSyncResult with full audit context and success/failure state.
        """
        customer_name = order.customer.customer_name if order.customer else None
        total_value = str(order.total) if order.total else None

        self.log.info(
            "order_sync_start",
            order_id=str(order.id),
            order_number=order.order_number,
            customer=customer_name,
            total=total_value,
            source_email=order.email_message_id,
            language=order.detected_language,
        )

        order.status = OrderStatus.SYNCING
        payload = _map_to_erp_payload(order, self.erp_provider)

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                erp_id = _push_to_erp(payload, self.erp_provider, order.order_number)

                order.status = OrderStatus.SYNCED
                order.erp_sync_id = erp_id

                self.log.info(
                    "order_sync_success",
                    order_id=str(order.id),
                    order_number=order.order_number,
                    erp_transaction_id=erp_id,
                    attempt=attempt,
                    customer=customer_name,
                    source_email=order.email_message_id,
                    extracted_fields={
                        "order_date": str(order.order_date),
                        "total": total_value,
                        "line_items": len(order.line_items),
                        "language": str(order.detected_language),
                    },
                )

                return OrderSyncResult(
                    order_id=str(order.id),
                    order_number=order.order_number,
                    erp_provider=self.erp_provider.value,
                    success=True,
                    erp_transaction_id=erp_id,
                    attempts=attempt,
                    source_email_id=order.email_message_id,
                    customer_name=customer_name,
                    total_value=total_value,
                    line_item_count=len(order.line_items),
                )

            except Exception as exc:
                self.log.warning(
                    "order_sync_retry",
                    order_id=str(order.id),
                    order_number=order.order_number,
                    attempt=attempt,
                    error=str(exc),
                )

                if attempt == MAX_RETRIES:
                    order.status = OrderStatus.FAILED
                    order.erp_sync_error = str(exc)

                    self.log.error(
                        "order_sync_failed",
                        order_id=str(order.id),
                        order_number=order.order_number,
                        error=str(exc),
                        source_email=order.email_message_id,
                        customer=customer_name,
                        total=total_value,
                    )

                    return OrderSyncResult(
                        order_id=str(order.id),
                        order_number=order.order_number,
                        erp_provider=self.erp_provider.value,
                        success=False,
                        error_message=str(exc),
                        attempts=attempt,
                        source_email_id=order.email_message_id,
                        customer_name=customer_name,
                        total_value=total_value,
                        line_item_count=len(order.line_items),
                    )

                time.sleep(RETRY_DELAY_SECONDS * attempt)

        # Unreachable but satisfies type checker
        return OrderSyncResult(
            order_id=str(order.id),
            order_number=order.order_number,
            erp_provider=self.erp_provider.value,
            success=False,
            error_message="Max retries exceeded",
            attempts=MAX_RETRIES,
        )
