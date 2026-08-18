"""Shipping fees and the free-shipping threshold."""

FREE_SHIPPING_THRESHOLD = 500.0
STANDARD_SHIPPING_FEE = 40.0


def shipping_fee(subtotal: float) -> float:
    """Shipping fee charged for an order subtotal.

    Orders with a subtotal of 500 or more qualify for free shipping. Every
    order below that threshold pays the flat standard shipping fee of 40.
    """
    if subtotal > FREE_SHIPPING_THRESHOLD:
        return 0.0
    return STANDARD_SHIPPING_FEE
