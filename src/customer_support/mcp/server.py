"""FastMCP server entrypoint and tools for the customer support demo."""

from __future__ import annotations

from typing import Annotated

from fastmcp import FastMCP
from pydantic import Field

from customer_support.core.models import (
    AuditEntry,
    Customer,
    Order,
    RefundRequest,
    RefundResponse,
    StoreCreditRequest,
    StoreCreditResponse,
)
from customer_support.core.support_service import CustomerSupportService

SERVER_INSTRUCTIONS = """
This server exposes a small customer support business layer through MCP tools.
Use lookup tools before mutating operations when customer or order context is uncertain.
Use store credit as the preferred non-destructive resolution when acceptable to the customer.
Use refunds only when the customer explicitly requests money back or policy requires it.
Mutating tools are idempotent through request_id, so safe retries should reuse the same request_id.
""".strip()


service = CustomerSupportService()

mcp = FastMCP(
    name="customer-support",
    instructions=SERVER_INSTRUCTIONS,
    version="0.1.0",
)


@mcp.tool(
    name="lookup_customer",
    title="Lookup Customer",
    description=(
        "Retrieve a concise customer profile by customer_id. Use this before "
        "taking customer-specific actions so the agent can confirm the customer "
        "exists and understand basic account context such as loyalty tier. "
        "Returns null when no matching customer is found."
    ),
    annotations={"readOnlyHint": True, "idempotentHint": True},
    meta={
        "returns": "Customer model with customer_id, name, email, and loyalty_tier, or null if not found.",
    },
)
def lookup_customer(
    customer_id: Annotated[
        str,
        Field(
            min_length=1,
            description="Stable customer identifier, for example 'cust_1001'.",
        ),
    ],
) -> Customer | None:
    return service.lookup_customer(customer_id)


@mcp.tool(
    name="lookup_order",
    title="Lookup Order",
    description=(
        "Retrieve a concise order summary by order_id. Use this to verify order "
        "ownership, payment status, fulfillment status, and order amount before "
        "considering a refund. Returns null when no matching order is found."
    ),
    annotations={"readOnlyHint": True, "idempotentHint": True},
    meta={
        "returns": "Order model with order_id, customer_id, amount, status, payment_status, and created_at, or null if not found.",
    },
)
def lookup_order(
    order_id: Annotated[
        str,
        Field(
            min_length=1,
            description="Stable order identifier, for example 'ord_5001'.",
        ),
    ],
) -> Order | None:
    return service.lookup_order(order_id)


@mcp.tool(
    name="add_store_credit",
    title="Add Store Credit",
    description=(
        "Issue store credit to a customer as a preferred, non-destructive support "
        "resolution. Store credit is usually faster than a monetary refund and "
        "keeps the customer relationship active. Use this when store credit is an "
        "acceptable remedy for the customer. The request_id makes retries safe: "
        "duplicate requests return the original stored response instead of issuing "
        "credit again. Returns a concise status response for agent use."
    ),
    annotations={"readOnlyHint": False, "idempotentHint": True},
    meta={
        "returns": "StoreCreditResponse with request_id, customer_id, amount, status, and message. The response represents the issued credit outcome; future versions may include updated balance.",
    },
)
def add_store_credit(request: StoreCreditRequest) -> StoreCreditResponse:
    return service.add_store_credit(request)


@mcp.tool(
    name="refund_payment",
    title="Refund Payment",
    description=(
        "Issue a monetary refund for a paid order. Use this only when the customer "
        "explicitly requests a refund or when policy requires money to be returned "
        "to the original payment path. Verify the customer and order first when "
        "possible. Retries are safe because request_id provides idempotency: a "
        "duplicate request returns the exact original response and does not process "
        "a second refund. The optional simulate_timeout flag is for retry-handling "
        "demos and raises a timeout before the refund transaction completes."
    ),
    annotations={"readOnlyHint": False, "idempotentHint": True},
    meta={
        "returns": "RefundResponse with request_id, customer_id, order_id, amount, status, and message.",
    },
)
def refund_payment(
    request: RefundRequest,
    simulate_timeout: Annotated[
        bool,
        Field(
            description="When true, simulate a timeout before completing the refund transaction. Use only for retry demonstrations.",
        ),
    ] = False,
) -> RefundResponse:
    return service.refund_payment(request, simulate_timeout=simulate_timeout)


@mcp.tool(
    name="get_audit_logs",
    title="Get Audit Logs",
    description=(
        "Return concise audit entries for mutating customer support operations. "
        "Use this to inspect what refunds and store credits were attempted, the "
        "request_id used for idempotency, and whether each operation was approved, "
        "issued, or rejected. This tool is read-only and does not expose raw rows."
    ),
    annotations={"readOnlyHint": True, "idempotentHint": True},
    meta={
        "returns": "List of AuditEntry models ordered by creation time.",
    },
)
def get_audit_logs() -> list[AuditEntry]:
    return service.get_audit_logs()


def create_server(test_service: CustomerSupportService | None = None) -> FastMCP:
    """Return the FastMCP server, optionally swapping in a test service."""
    global service
    if test_service is not None:
        service = test_service
    return mcp


def main() -> None:
    """Run the MCP server over Streamable HTTP for ADK clients."""
    mcp.run(
        transport="streamable-http",
        host="127.0.0.1",
        port=9000,
        path="/mcp",
    )


if __name__ == "__main__":
    main()
