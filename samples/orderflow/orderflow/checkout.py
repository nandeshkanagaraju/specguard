"""Checkout orchestration: validate, reserve stock, authorise payment, receipt."""

from .pricing import apply_discount, calculate_tax
from .shipping import shipping_fee


class InvalidOrder(Exception):
    """Raised when an order fails validation, before any side effect occurs."""


class PaymentDeclined(Exception):
    """Raised when the gateway refuses to authorise the order total."""


def validate_order(order: dict) -> None:
    """Reject an order containing any item with a quantity below 1.

    Validation runs before stock is touched, so a rejected order leaves no
    reservations behind.
    """
    if not order.get("items"):
        raise InvalidOrder("order contains no items")
    for item in order["items"]:
        if item["quantity"] < 1:
            raise InvalidOrder(
                f"item {item['sku']} has quantity {item['quantity']}, minimum is 1"
            )


def order_total(order: dict) -> dict:
    """Money owed for an order: subtotal, discount, tax and shipping."""
    subtotal = sum(i["unit_price"] * i["quantity"] for i in order["items"])
    discounted = apply_discount(subtotal, order.get("discount_codes", []))
    tax = calculate_tax(discounted)
    freight = shipping_fee(subtotal)
    return {
        "subtotal": round(subtotal, 2),
        "discounted_subtotal": discounted,
        "tax": tax,
        "shipping": freight,
        "total": round(discounted + tax + freight, 2),
    }


def reserve_stock(order: dict, warehouse, now=None) -> list:
    """Reserve stock in the warehouse for every line of the order."""
    reservations = []
    for item in order["items"]:
        reservations.append(
            warehouse.reserve(order["id"], item["sku"], item["quantity"], now=now)
        )
    return reservations


def build_receipt(order: dict, money: dict) -> dict:
    """Receipt for a completed order: the order id and the total charged."""
    lines = []
    for item in order["items"]:
        lines.append({"sku": item["sku"], "quantity": item["quantity"]})
    return {
        "order_id": order["id"],
        "total": money["total"],
        "lines": lines,
    }


def log_payment_failure(order_id: str) -> None:
    """Record a declined authorisation against the order."""
    FAILED_AUTHORISATIONS.append(order_id)


FAILED_AUTHORISATIONS: list[str] = []


def checkout(order: dict, warehouse, gateway, now=None) -> dict:
    """Take one order from validation through stock reservation to payment.

    Stock is reserved before the payment is authorised, and a declined payment
    leaves that reservation in place.
    """
    validate_order(order)
    money = order_total(order)

    reserve_stock(order, warehouse, now=now)

    try:
        gateway.authorise(order["id"], money["total"])
    except PaymentDeclined:
        log_payment_failure(order["id"])
        raise

    return build_receipt(order, money)
