"""OrderFlow's own test suite.

Read this file with the SPEC next to it. The suite is realistic — it is the kind
of suite a team actually writes — and it is green on BOTH the clean and the
drifted variant of the service. That is the entire point of SpecGuard: passing
tests do not mean the code still matches the specification.
"""

from datetime import datetime, timedelta

import pytest

from orderflow.checkout import (
    InvalidOrder,
    PaymentDeclined,
    build_receipt,
    checkout,
    order_total,
    validate_order,
)
from orderflow.inventory import OutOfStock, Warehouse
from orderflow.pricing import apply_discount, calculate_tax, discount_rate
from orderflow.shipping import shipping_fee

T0 = datetime(2026, 1, 1, 12, 0, 0)


class AcceptingGateway:
    def __init__(self):
        self.calls = []

    def authorise(self, order_id, amount):
        self.calls.append((order_id, amount))
        return {"authorisation": "auth-1", "amount": amount}


class DecliningGateway:
    def authorise(self, order_id, amount):
        raise PaymentDeclined(f"card declined for {order_id}")


def make_order(**overrides):
    order = {
        "id": "ORD-1",
        "items": [{"sku": "SKU-A", "quantity": 2, "unit_price": 100.0}],
        "discount_codes": [],
    }
    order.update(overrides)
    return order


# ------------------------------------------------------------------ pricing


def test_discount_applies_to_subtotal():
    assert apply_discount(200.0, ["WELCOME10"]) == 180.0


def test_discount_is_capped():
    assert discount_rate(["VIP30", "LOYAL20"]) == 0.40
    assert apply_discount(100.0, ["VIP30", "LOYAL20"]) == 60.0


def test_unknown_code_is_ignored():
    assert apply_discount(100.0, ["NOPE"]) == 100.0


def test_tax_is_eight_percent():
    assert calculate_tax(200.0) == 16.0


# ----------------------------------------------------------------- shipping


def test_small_order_pays_flat_fee():
    assert shipping_fee(499.99) == 40.0
    assert shipping_fee(120.0) == 40.0


def test_large_order_ships_free():
    assert shipping_fee(600.0) == 0.0
    assert shipping_fee(1000.0) == 0.0


# ---------------------------------------------------------------- inventory


def test_reserve_decrements_stock():
    w = Warehouse("WH-1", {"SKU-A": 10})
    w.reserve("ORD-1", "SKU-A", 3, now=T0)
    assert w.available("SKU-A") == 7


def test_reserve_beyond_stock_raises():
    w = Warehouse("WH-1", {"SKU-A": 1})
    with pytest.raises(OutOfStock):
        w.reserve("ORD-1", "SKU-A", 2, now=T0)


def test_reservation_is_scoped_to_its_warehouse():
    a = Warehouse("WH-1", {"SKU-A": 5})
    b = Warehouse("WH-2", {"SKU-A": 5})
    a.reserve("ORD-1", "SKU-A", 5, now=T0)
    assert a.available("SKU-A") == 0
    assert b.available("SKU-A") == 5


def test_expired_reservation_returns_stock():
    w = Warehouse("WH-1", {"SKU-A": 4})
    w.reserve("ORD-1", "SKU-A", 4, now=T0)
    assert w.release_expired(now=T0 + timedelta(minutes=5)) == []
    assert w.available("SKU-A") == 0
    released = w.release_expired(now=T0 + timedelta(minutes=20))
    assert len(released) == 1
    assert w.available("SKU-A") == 4


# ----------------------------------------------------------------- checkout


def test_empty_order_is_rejected():
    with pytest.raises(InvalidOrder):
        validate_order(make_order(items=[]))


def test_order_total_composes_the_money():
    money = order_total(make_order())
    assert money["subtotal"] == 200.0
    assert money["tax"] == 16.0
    assert money["shipping"] == 40.0
    assert money["total"] == 256.0


def test_receipt_carries_order_id_and_total():
    order = make_order()
    receipt = build_receipt(order, order_total(order))
    assert receipt["order_id"] == "ORD-1"
    assert receipt["total"] == 256.0


def test_checkout_happy_path():
    w = Warehouse("WH-1", {"SKU-A": 10})
    gateway = AcceptingGateway()
    receipt = checkout(make_order(), w, gateway, now=T0)
    assert receipt["order_id"] == "ORD-1"
    assert receipt["total"] == 256.0
    assert w.available("SKU-A") == 8
    assert gateway.calls == [("ORD-1", 256.0)]


def test_declined_payment_raises_payment_declined():
    w = Warehouse("WH-1", {"SKU-A": 10})
    with pytest.raises(PaymentDeclined):
        checkout(make_order(), w, DecliningGateway(), now=T0)
