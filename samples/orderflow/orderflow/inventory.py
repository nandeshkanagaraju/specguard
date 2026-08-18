"""Stock reservation, scoped to one warehouse and one SKU at a time."""

from datetime import datetime, timedelta

RESERVATION_TTL_MINUTES = 15


class OutOfStock(Exception):
    """Raised when a SKU does not hold enough stock to satisfy a reservation."""


class Reservation:
    """One reservation of one SKU, held inside exactly one warehouse."""

    def __init__(self, order_id, sku, quantity, created_at, warehouse_id):
        self.order_id = order_id
        self.sku = sku
        self.quantity = quantity
        self.created_at = created_at
        self.warehouse_id = warehouse_id

    def is_expired(self, now: datetime) -> bool:
        """A reservation expires 15 minutes after it was created."""
        age = now - self.created_at
        return age >= timedelta(minutes=RESERVATION_TTL_MINUTES)


class Warehouse:
    """Stock levels and open reservations for a single warehouse."""

    def __init__(self, warehouse_id: str, stock: dict[str, int] | None = None):
        self.warehouse_id = warehouse_id
        self.stock = dict(stock or {})
        self.reservations: dict[tuple[str, str], Reservation] = {}

    def available(self, sku: str) -> int:
        """Units of the SKU currently free to reserve in this warehouse."""
        return self.stock.get(sku, 0)

    def reserve(self, order_id: str, sku: str, quantity: int, now=None) -> Reservation:
        """Reserve stock for a single SKU inside this warehouse.

        A reservation is per SKU and never spans warehouses: it is keyed by
        (order id, sku) in this warehouse's own ledger and only ever decrements
        this warehouse's stock.
        """
        now = now or datetime(2026, 1, 1, 12, 0, 0)
        on_hand = self.available(sku)
        if on_hand < quantity:
            raise OutOfStock(f"{sku}: {on_hand} on hand, {quantity} requested")
        self.stock[sku] = on_hand - quantity
        reservation = Reservation(order_id, sku, quantity, now, self.warehouse_id)
        self.reservations[(order_id, sku)] = reservation
        return reservation

    def release_expired(self, now=None) -> list[Reservation]:
        """Return stock to the pool for every reservation past its 15 minute expiry."""
        now = now or datetime(2026, 1, 1, 12, 0, 0)
        released = []
        for key, reservation in list(self.reservations.items()):
            if reservation.is_expired(now):
                self.stock[reservation.sku] = self.available(reservation.sku) + reservation.quantity
                del self.reservations[key]
                released.append(reservation)
        return released
