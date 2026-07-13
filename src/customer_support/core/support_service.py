"""Business logic for customer support operations."""

from __future__ import annotations

from datetime import UTC, datetime

from customer_support.core.audit import AuditLogger
from customer_support.core.database import DEFAULT_DB_PATH
from customer_support.core.models import (
    Customer,
    Order,
    RefundRequest,
    RefundResponse,
    StoreCreditRequest,
    StoreCreditResponse,
    AuditEntry,
)
from customer_support.core.repository import SupportRepository


class CustomerSupportService:
    """Framework-independent business service."""

    def __init__(self, repository: SupportRepository | None = None) -> None:
        self.repository = repository or SupportRepository(DEFAULT_DB_PATH)
        self.audit_logger = AuditLogger(self.repository)

    def lookup_customer(self, customer_id: str) -> Customer | None:
        row = self.repository.get_customer(customer_id)
        return Customer(**dict(row)) if row else None

    def lookup_order(self, order_id: str) -> Order | None:
        row = self.repository.get_order(order_id)
        if not row:
            return None
        data = dict(row)
        data["created_at"] = datetime.fromisoformat(data["created_at"])
        return Order(**data)

    def add_store_credit(
        self, request: StoreCreditRequest
    ) -> StoreCreditResponse:
        with self.repository.transaction() as connection:
            saved_response = self.repository.get_processed_response(
                connection, request.request_id
            )
            if saved_response:
                return StoreCreditResponse.model_validate_json(saved_response)

            customer = self.repository.get_customer_for_update(
                connection, request.customer_id
            )
            response = (
                StoreCreditResponse(
                    request_id=request.request_id,
                    customer_id=request.customer_id,
                    amount=request.amount,
                    status="issued",
                    message="Store credit issued.",
                )
                if customer
                else StoreCreditResponse(
                    request_id=request.request_id,
                    customer_id=request.customer_id,
                    amount=request.amount,
                    status="rejected",
                    message="Customer not found.",
                )
            )

            now = datetime.now(UTC)
            if response.status == "issued":
                self.repository.insert_store_credit(
                    connection,
                    request.request_id,
                    request.customer_id,
                    request.amount,
                    request.reason,
                    now,
                )
            self.repository.save_processed_response(
                connection,
                request.request_id,
                "store_credit",
                response.model_dump_json(),
                now,
            )
            self.audit_logger.log(
                connection,
                action="store_credit",
                request_id=request.request_id,
                customer_id=request.customer_id,
                order_id=None,
                amount=request.amount,
                status=response.status,
            )
            return response

    def refund_payment(
        self, request: RefundRequest, simulate_timeout: bool = False
    ) -> RefundResponse:
        with self.repository.transaction() as connection:
            saved_response = self.repository.get_processed_response(
                connection, request.request_id
            )
            if saved_response:
                return RefundResponse.model_validate_json(saved_response)

            if simulate_timeout:
                raise TimeoutError("Simulated payment processor timeout.")

            customer = self.repository.get_customer_for_update(
                connection, request.customer_id
            )
            order = self.repository.get_order_for_update(connection, request.order_id)
            response = self._build_refund_response(request, bool(customer), order)

            now = datetime.now(UTC)
            if response.status == "approved":
                self.repository.insert_refund(
                    connection,
                    request.request_id,
                    request.customer_id,
                    request.order_id,
                    request.amount,
                    request.reason,
                    now,
                )
            self.repository.save_processed_response(
                connection,
                request.request_id,
                "refund",
                response.model_dump_json(),
                now,
            )
            self.audit_logger.log(
                connection,
                action="refund",
                request_id=request.request_id,
                customer_id=request.customer_id,
                order_id=request.order_id,
                amount=request.amount,
                status=response.status,
            )
            return response

    def get_audit_logs(self) -> list[AuditEntry]:
        return self.audit_logger.get_audit_logs()

    @staticmethod
    def _build_refund_response(
        request: RefundRequest, customer_exists: bool, order: object | None
    ) -> RefundResponse:
        if not customer_exists:
            status = "rejected"
            message = "Customer not found."
        elif not order:
            status = "rejected"
            message = "Order not found."
        elif order["customer_id"] != request.customer_id:
            status = "rejected"
            message = "Order does not belong to customer."
        elif request.amount > float(order["amount"]):
            status = "rejected"
            message = "Refund amount exceeds order total."
        else:
            status = "approved"
            message = "Refund approved."

        return RefundResponse(
            request_id=request.request_id,
            customer_id=request.customer_id,
            order_id=request.order_id,
            amount=request.amount,
            status=status,
            message=message,
        )


_default_service = CustomerSupportService()


def lookup_customer(customer_id: str) -> Customer | None:
    return _default_service.lookup_customer(customer_id)


def lookup_order(order_id: str) -> Order | None:
    return _default_service.lookup_order(order_id)


def add_store_credit(request: StoreCreditRequest) -> StoreCreditResponse:
    return _default_service.add_store_credit(request)


def refund_payment(
    request: RefundRequest, simulate_timeout: bool = False
) -> RefundResponse:
    return _default_service.refund_payment(request, simulate_timeout)


def get_audit_logs() -> list[AuditEntry]:
    return _default_service.get_audit_logs()
