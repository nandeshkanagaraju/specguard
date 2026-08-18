# OrderFlow — Service Specification

OrderFlow prices a basket, reserves stock, takes payment, and returns a receipt.
This document is the contract. Every numbered rule below is atomic and testable.

## Rules

### Pricing

- Discount codes apply to the subtotal before tax.
- The maximum total discount is 40% of the subtotal.
- Tax is calculated at 8% of the discounted subtotal.

### Shipping

- Orders with a subtotal of 500 or more qualify for free shipping.
- Standard shipping is a flat 40 for orders below the free-shipping threshold.

### Checkout sequence

- Stock must be reserved before payment is authorised.

### Inventory

- A reservation expires after 15 minutes and returns stock to the pool.

### Checkout

- The checkout must reject an order containing any item with quantity below 1.
- A failed payment must raise `PaymentDeclined` and leave stock reserved.
- Every completed order returns a receipt containing the order id and total.

### Reservations

- Reservations are per SKU and never span warehouses.

### Non-functional

- The checkout should feel fast for the user.
