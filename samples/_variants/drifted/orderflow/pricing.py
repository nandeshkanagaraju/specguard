"""Pricing: discount codes and tax."""

MAX_DISCOUNT_RATE = 0.40
TAX_RATE = 0.08

DISCOUNT_CODES = {
    "WELCOME10": 0.10,
    "SPRING15": 0.15,
    "LOYAL20": 0.20,
    "VIP30": 0.30,
}


def discount_rate(discount_codes: list[str]) -> float:
    """Combined discount rate for the codes, capped at the maximum of 40%.

    Unknown codes contribute nothing.
    """
    raw = sum(DISCOUNT_CODES.get(code, 0.0) for code in discount_codes)
    return min(raw, MAX_DISCOUNT_RATE)


def apply_discount(subtotal: float, discount_codes: list[str]) -> float:
    """Apply the discount codes to the subtotal, before any tax is added.

    The maximum total discount is 40% of the subtotal.
    """
    rate = discount_rate(discount_codes)
    return round(subtotal * (1.0 - rate), 2)


def calculate_tax(discounted_subtotal: float) -> float:
    """Tax is 8% of the discounted subtotal."""
    return round(discounted_subtotal * TAX_RATE, 2)
