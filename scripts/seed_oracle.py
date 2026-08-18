"""Build samples/orderflow/.specguard_oracle.json for both fixture variants.

This is the *seeding* path: the judgements below are authored, then compiled into
the same on-disk format `specguard record-oracle` produces from a live model. The
compiler is what makes them trustworthy — every evidence anchor must resolve to
real lines in the real prompt, or the build fails loudly rather than shipping a
citation that points at nothing.

Run:  python scripts/seed_oracle.py
Then: specguard record-oracle --provider anthropic   # to replace with live output
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "src"))

from specguard.config import load_config  # noqa: E402
from specguard.indexer import index_repo  # noqa: E402
from specguard.oracle import (  # noqa: E402
    ORACLE_FILENAME,
    entry_key,
    read_prompt,
    save_oracle,
)
from specguard.prompts import PROMPT_VERSION, pass_a_user, pass_b_user  # noqa: E402
from specguard.retriever import LexicalRetriever  # noqa: E402
from specguard.spec_parser import parse_spec  # noqa: E402

FIXTURE = ROOT / "samples" / "orderflow"
VARIANTS = ROOT / "samples" / "_variants"

PRICING = "orderflow/pricing.py"
SHIPPING = "orderflow/shipping.py"
INVENTORY = "orderflow/inventory.py"
CHECKOUT = "orderflow/checkout.py"

# ---------------------------------------------------------------------------
# The authored judgements. Keys are (variant, rule_id); "*" means the judgement
# holds for both variants because the relevant code is byte-identical.
# ---------------------------------------------------------------------------

SEED: dict[tuple[str, str], dict] = {}


def seed(variant, rule_id, *, verdict, reasoning, evidence=(), category=None,
         confidence=0.9, b_overturned=False, b_argument="", b_confidence=0.2,
         present=(), absent=()):
    SEED[(variant, rule_id)] = {
        "a": {
            "verdict": verdict,
            "category": category,
            "confidence": confidence,
            "evidence": [{"path": p, "anchor": a} for p, a in evidence],
            "reasoning": reasoning,
        },
        "b": {
            "overturned": b_overturned,
            "argument": b_argument,
            "confidence": b_confidence,
        },
        "present": list(present),
        "absent": list(absent),
    }


# --- rules whose code is identical in both variants ------------------------

seed(
    "*", "R-001",
    verdict="ALIGNED", confidence=0.93,
    evidence=[(PRICING, '    rate = discount_rate(discount_codes)\n'
                        '    return round(subtotal * (1.0 - rate), 2)')],
    reasoning="apply_discount scales the raw subtotal by the discount rate and returns "
              "the result, with no tax term anywhere in the expression. Tax is applied "
              "separately by calculate_tax on that already-discounted figure.",
    b_argument="One could argue the ordering is only implicit here, since apply_discount "
               "never names tax. It is not a real objection: the function receives the "
               "pre-tax subtotal and the caller applies tax to its output.",
    present=['    rate = discount_rate(discount_codes)'],
)

seed(
    "*", "R-002",
    verdict="ALIGNED", confidence=0.95,
    evidence=[(PRICING, '    return min(raw, MAX_DISCOUNT_RATE)')],
    reasoning="discount_rate sums the matched codes and clamps the total with "
              "min(raw, MAX_DISCOUNT_RATE), where MAX_DISCOUNT_RATE is 0.40. Stacked "
              "codes therefore cannot exceed 40% of the subtotal.",
    b_argument="The strongest counter would be that the cap applies to the rate rather "
               "than the money, but since the rate multiplies the subtotal directly the "
               "two are the same constraint. No overturn.",
    present=['    return min(raw, MAX_DISCOUNT_RATE)'],
)

seed(
    "*", "R-003",
    verdict="ALIGNED", confidence=0.94,
    evidence=[(PRICING, '    return round(discounted_subtotal * TAX_RATE, 2)')],
    reasoning="calculate_tax multiplies its argument by TAX_RATE, which is 0.08, and the "
              "parameter is named discounted_subtotal. The rate and the base both match "
              "the rule.",
    b_argument="I looked for a rounding objection — round() to two places could in "
               "principle shift the effective rate — but the rule states no rounding "
               "requirement, so inventing one would be over-reach.",
    present=['    return round(discounted_subtotal * TAX_RATE, 2)'],
)

seed(
    "*", "R-007",
    verdict="ALIGNED", confidence=0.91,
    evidence=[
        (INVENTORY, '        return age >= timedelta(minutes=RESERVATION_TTL_MINUTES)'),
        (INVENTORY, '            if reservation.is_expired(now):\n'
                    '                self.stock[reservation.sku] = self.available('
                    'reservation.sku) + reservation.quantity'),
    ],
    reasoning="is_expired treats a reservation as expired once its age reaches the "
              "15-minute TTL, and release_expired adds the reserved quantity back to "
              "self.stock for each expired reservation. Both halves of the rule are "
              "implemented.",
    b_argument="An objection could be built around >= versus > at exactly 15 minutes, "
               "but the rule says 'after 15 minutes' without fixing the boundary, so "
               "either comparison satisfies it. No overturn.",
    present=['        return age >= timedelta(minutes=RESERVATION_TTL_MINUTES)'],
)

seed(
    "*", "R-011",
    verdict="ALIGNED", confidence=0.82,
    evidence=[(INVENTORY, '        reservation = Reservation(order_id, sku, quantity, '
                          'now, self.warehouse_id)\n'
                          '        self.reservations[(order_id, sku)] = reservation')],
    reasoning="reserve keys each reservation by (order_id, sku) in the warehouse "
              "instance's own ledger and stamps it with self.warehouse_id, so a "
              "reservation is scoped to one SKU in one warehouse. Nothing in the class "
              "reads or writes another warehouse's stock.",
    b_argument="The honest counter is that nothing structurally prevents a caller from "
               "reserving the same SKU in two warehouses for one order. That is not what "
               "the rule forbids — it forbids a single reservation spanning warehouses — "
               "so the verdict stands.",
    present=['        self.reservations[(order_id, sku)] = reservation'],
)

# --- shipping: clean vs drifted -------------------------------------------

seed(
    "clean", "R-004",
    verdict="ALIGNED", confidence=0.94,
    evidence=[(SHIPPING, '    if subtotal >= FREE_SHIPPING_THRESHOLD:\n        return 0.0')],
    reasoning="shipping_fee compares the subtotal to FREE_SHIPPING_THRESHOLD with >=, so "
              "an order of exactly 500 returns a fee of 0.0. The inclusive boundary "
              "matches '500 or more'.",
    b_argument="To overturn this I would need the threshold constant to differ from 500, "
               "but it is defined as 500.0 in the same module. No counter-argument holds.",
    present=['    if subtotal >= FREE_SHIPPING_THRESHOLD:'],
)

seed(
    "drifted", "R-004",
    verdict="DRIFTED", category="D1", confidence=0.93,
    evidence=[
        (SHIPPING, '    if subtotal > FREE_SHIPPING_THRESHOLD:\n        return 0.0'),
        (SHIPPING, 'FREE_SHIPPING_THRESHOLD = 500.0'),
    ],
    reasoning="The rule grants free shipping at a subtotal of 500 or more, but the "
              "comparison is a strict greater-than against a threshold of 500.0. An order "
              "of exactly 500.00 falls through and is charged the standard fee.",
    b_argument="The best case for the code is that a subtotal landing on exactly 500.00 "
               "is rare in float arithmetic. That is a probability argument, not a "
               "conformance one — the spec fixes the boundary explicitly.",
    b_confidence=0.25,
    present=['    if subtotal > FREE_SHIPPING_THRESHOLD:'],
)

seed(
    "clean", "R-005",
    verdict="ALIGNED", confidence=0.92,
    evidence=[
        (SHIPPING, '    return STANDARD_SHIPPING_FEE'),
        (SHIPPING, 'STANDARD_SHIPPING_FEE = 40.0'),
    ],
    reasoning="Any subtotal that fails the free-shipping test falls through to "
              "STANDARD_SHIPPING_FEE, which is 40.0, with no proportional component. "
              "That is the flat fee the rule requires.",
    b_argument="No honest counter-argument: the fee is a single module constant returned "
               "unconditionally on the below-threshold path.",
    present=['    if subtotal >= FREE_SHIPPING_THRESHOLD:'],
)

seed(
    "drifted", "R-005",
    verdict="ALIGNED", confidence=0.88,
    evidence=[
        (SHIPPING, '    return STANDARD_SHIPPING_FEE'),
        (SHIPPING, 'STANDARD_SHIPPING_FEE = 40.0'),
    ],
    reasoning="Orders below the threshold return STANDARD_SHIPPING_FEE, a flat 40.0. This "
              "rule constrains the amount charged below the threshold, not where the "
              "threshold itself sits, and the amount is correct.",
    b_argument="The set of orders treated as 'below the threshold' has changed, which "
               "arguably touches this rule. But the fee charged to them is still a flat "
               "40, which is all this rule asks; the boundary is R-004's concern.",
    b_confidence=0.35,
    present=['    if subtotal > FREE_SHIPPING_THRESHOLD:'],
)

# --- checkout: clean vs drifted -------------------------------------------

seed(
    "clean", "R-006",
    verdict="ALIGNED", confidence=0.92,
    evidence=[(CHECKOUT, '    reserve_stock(order, warehouse, now=now)\n'
                         '\n'
                         '    try:\n'
                         '        gateway.authorise(order["id"], money["total"])')],
    reasoning="checkout calls reserve_stock before entering the try block that authorises "
              "payment, so stock is held before the gateway is contacted. The statement "
              "order matches the rule.",
    b_argument="I considered arguing that reserve_stock might defer its work, but it "
               "loops and calls warehouse.reserve synchronously. No overturn.",
    present=['    except PaymentDeclined:'],
)

seed(
    "drifted", "R-006",
    verdict="DRIFTED", category="D5", confidence=0.90,
    evidence=[(CHECKOUT, '    try:\n'
                         '        gateway.authorise(order["id"], money["total"])\n'
                         '    except Exception:\n'
                         '        log_payment_failure(order["id"])\n'
                         '        raise PaymentDeclined(order["id"])\n'
                         '\n'
                         '    reserve_stock(order, warehouse, now=now)')],
    reasoning="The rule requires stock to be reserved before payment is authorised, but "
              "gateway.authorise runs first and reserve_stock only afterwards. A customer "
              "can be charged for units another order takes in the interval.",
    b_argument="The only defence available is that the docstring still describes the "
               "correct order, which is not implementation. The executable statement "
               "order contradicts the rule.",
    b_confidence=0.15,
    present=['    except Exception:'],
)

seed(
    "clean", "R-008",
    verdict="ALIGNED", confidence=0.93,
    evidence=[(CHECKOUT, '    for item in order["items"]:\n'
                         '        if item["quantity"] < 1:')],
    reasoning="validate_order iterates the line items and raises InvalidOrder for any "
              "quantity below 1. The rejection the rule asks for is implemented and "
              "reached before any side effect.",
    b_argument="A counter would need the check to be unreachable or the comparison to be "
               "wrong; it is neither. No overturn.",
    present=['        if item["quantity"] < 1:'],
)

seed(
    "drifted", "R-008",
    verdict="DRIFTED", category="D2", confidence=0.94,
    evidence=[
        (CHECKOUT, '    """Reject an order containing any item with a quantity below 1.'),
        (CHECKOUT, '    if not order.get("items"):\n'
                   '        raise InvalidOrder("order contains no items")'),
    ],
    reasoning="validate_order now only rejects an order with no items at all; nothing "
              "inspects per-item quantity, so an item with quantity 0 or -3 passes "
              "validation. The docstring still promises the check that the body no longer "
              "performs.",
    b_argument="One could hope the quantity check moved to order_total or reserve_stock, "
               "but neither compares quantity to 1 — reserve_stock passes the value "
               "straight through to the warehouse.",
    b_confidence=0.2,
    absent=['        if item["quantity"] < 1:'],
    present=['    """Reject an order containing any item with a quantity below 1.'],
)

seed(
    "clean", "R-009",
    verdict="ALIGNED", confidence=0.91,
    evidence=[(CHECKOUT, '    except PaymentDeclined:\n'
                         '        log_payment_failure(order["id"])\n'
                         '        raise')],
    reasoning="A declined authorisation is caught, logged, and re-raised bare, so "
              "PaymentDeclined reaches the caller. Nothing on that path releases the "
              "reservation made earlier in the function.",
    b_argument="The nearest objection is that log_payment_failure runs before the "
               "re-raise, but it only appends an id to a list and cannot release stock.",
    present=['    except PaymentDeclined:'],
)

seed(
    "drifted", "R-009",
    verdict="DRIFTED", category="D7", confidence=0.78,
    evidence=[(CHECKOUT, '    except Exception:\n'
                         '        log_payment_failure(order["id"])\n'
                         '        raise PaymentDeclined(order["id"])')],
    reasoning="The handler catches bare Exception rather than PaymentDeclined, so any "
              "failure from the gateway — a timeout, a bad response — is relabelled as a "
              "declined payment. The rule ties PaymentDeclined specifically to a failed "
              "payment.",
    b_overturned=True,
    b_argument="Read literally, the rule asks for two things on a failed payment: that "
               "PaymentDeclined is raised, and that stock stays reserved. This code does "
               "raise PaymentDeclined and never releases stock, so the rule as written is "
               "satisfied — the broad catch is a separate defect the rule does not "
               "mention.",
    b_confidence=0.66,
    present=['    except Exception:'],
)

seed(
    "clean", "R-010",
    verdict="ALIGNED", confidence=0.93,
    evidence=[(CHECKOUT, '    return {\n'
                         '        "order_id": order["id"],\n'
                         '        "total": money["total"],')],
    reasoning="build_receipt returns a dict carrying order_id and total, and checkout "
              "returns its result on the completed path. Both required fields are "
              "present.",
    b_argument="No honest counter-argument; both keys are set unconditionally.",
    present=['        lines.append({"sku": item["sku"], "quantity": item["quantity"]})'],
)

seed(
    "drifted", "R-010",
    verdict="ALIGNED", confidence=0.92,
    evidence=[(CHECKOUT, '    return {\n'
                         '        "order_id": order["id"],\n'
                         '        "total": money["total"],')],
    reasoning="build_receipt has been rewritten to build its line items with a "
              "comprehension, but it still returns order_id and total unconditionally. "
              "The change is behaviour-preserving with respect to this rule.",
    b_argument="The function was edited, which invites suspicion, but the edit only "
               "replaces an accumulator loop with an equivalent comprehension. Rewriting "
               "is not drift.",
    b_confidence=0.18,
    present=['            for item in order["items"]'],
)


# ---------------------------------------------------------------------------


def set_variant(variant: str) -> None:
    src = VARIANTS / variant / "orderflow"
    for f in sorted(src.glob("*.py")):
        shutil.copy2(f, FIXTURE / "orderflow" / f.name)


def compile_oracle() -> dict:
    entries: list[dict] = []
    seen: set[str] = set()
    problems: list[str] = []

    for variant in ("clean", "drifted"):
        set_variant(variant)
        cfg = load_config(FIXTURE)
        rules = parse_spec(FIXTURE / cfg.spec_path)
        chunks = index_repo(FIXTURE)
        retriever = LexicalRetriever(top_k=cfg.top_k, floor=cfg.floor)

        for rule in rules:
            if rule.unverifiable:
                continue
            spec = SEED.get((variant, rule.id)) or SEED.get(("*", rule.id))
            if spec is None:
                problems.append(f"{variant}/{rule.id}: no seeded judgement")
                continue

            candidates = retriever.rank(rule, chunks)
            if not candidates:
                problems.append(f"{variant}/{rule.id}: no candidates retrieved")
                continue

            user_a = pass_a_user(rule, candidates)
            view = read_prompt(user_a)

            for ev in spec["a"]["evidence"]:
                if view.resolve_anchor(ev["path"], ev["anchor"]) is None:
                    problems.append(
                        f"{variant}/{rule.id}: anchor does not resolve in "
                        f"{ev['path']}: {ev['anchor'].splitlines()[0]!r}"
                    )

            source = view.plain_source()
            for d in spec["present"]:
                if d not in source:
                    problems.append(f"{variant}/{rule.id}: discriminator absent: {d!r}")
            for d in spec["absent"]:
                if d in source:
                    problems.append(f"{variant}/{rule.id}: negative discriminator present: {d!r}")

            key_a = entry_key("A", user_a)
            if key_a not in seen:
                seen.add(key_a)
                entries.append({
                    "key": key_a,
                    "rule_id": rule.id,
                    "pass": "A",
                    "variant": variant,
                    "discriminators": spec["present"],
                    "discriminators_absent": spec["absent"],
                    "response": spec["a"],
                })

            user_b = pass_b_user(
                rule, candidates, spec["a"]["verdict"], spec["a"]["reasoning"]
            )
            key_b = entry_key("B", user_b)
            if key_b not in seen:
                seen.add(key_b)
                entries.append({
                    "key": key_b,
                    "rule_id": rule.id,
                    "pass": "B",
                    "variant": variant,
                    "discriminators": spec["present"],
                    "discriminators_absent": spec["absent"],
                    "response": spec["b"],
                })

    set_variant("clean")

    if problems:
        for p in problems:
            print(f"  FAIL  {p}", file=sys.stderr)
        raise SystemExit(f"{len(problems)} oracle problem(s); nothing written")

    return {
        "prompt_version": PROMPT_VERSION,
        "model_id": "mock-v1",
        "source": "seeded",
        "note": (
            "Recorded conformance judgements for the orderflow fixture. Evidence is "
            "stored as verbatim source anchors and re-resolved to line numbers at "
            "replay time, so a citation can never point at code that is not there. "
            "Regenerate from a live model with `specguard record-oracle`."
        ),
        "entries": entries,
    }


def main() -> None:
    data = compile_oracle()
    out = FIXTURE / ORACLE_FILENAME
    save_oracle(out, data)
    print(f"wrote {out.relative_to(ROOT)} — {len(data['entries'])} entries")


if __name__ == "__main__":
    main()
