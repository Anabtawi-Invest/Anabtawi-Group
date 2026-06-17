# POS Force Payment On Free Orders

This module forces creation of a POS payment line when an order is marked as paid and its total is `0.0`.

## Behavior

- Keeps the default POS flow.
- After normal payment processing, if the order has:
  - no payment lines,
  - not a draft state, and
  - total amount equal to zero,
  this module creates a zero-value payment line automatically.
- It picks the first non `pay_later` payment method from the session. If not found, it falls back to the first available method.
