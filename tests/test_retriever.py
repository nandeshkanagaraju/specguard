from __future__ import annotations

from specguard.indexer import index_repo
from specguard.models import Rule, sha256
from specguard.retriever import LexicalRetriever, numbers_in, score_pair, tokenize
from specguard.spec_parser import parse_spec


def rules_of(root):
    return {r.id: r for r in parse_spec(root / "SPEC.md")}


def test_r004_ranks_shipping_fee_first(fixture_repo):
    root = fixture_repo()
    chunks = index_repo(root)
    top = LexicalRetriever(3, 0.15).rank(rules_of(root)["R-004"], chunks)
    assert top[0].chunk.id == "orderflow/shipping.py::shipping_fee"
    assert top[0].score > 0.5


def test_every_verifiable_rule_reaches_its_module(fixture_repo):
    root = fixture_repo()
    chunks = index_repo(root)
    retriever = LexicalRetriever(3, 0.15)
    expected = {
        "R-001": "orderflow/pricing.py",
        "R-002": "orderflow/pricing.py",
        "R-003": "orderflow/pricing.py",
        "R-004": "orderflow/shipping.py",
        "R-005": "orderflow/shipping.py",
        "R-006": "orderflow/checkout.py",
        "R-007": "orderflow/inventory.py",
        "R-008": "orderflow/checkout.py",
        "R-009": "orderflow/checkout.py",
        "R-010": "orderflow/checkout.py",
        "R-011": "orderflow/inventory.py",
    }
    for rule_id, path in expected.items():
        top = retriever.rank(rules_of(root)[rule_id], chunks)
        assert top, f"{rule_id} retrieved nothing"
        assert top[0].chunk.path == path, f"{rule_id} went to {top[0].chunk.id}"


def test_numeric_literal_bonus_fires(fixture_repo):
    """The 500 in the rule is what makes boundary drift retrievable."""
    root = fixture_repo()
    fee = next(c for c in index_repo(root) if c.name == "shipping_fee")

    with_number = Rule(
        id="R-X", text="Orders with a subtotal of 500 or more qualify for free shipping.",
        section="Shipping", hash=sha256("x"),
    )
    without = Rule(
        id="R-Y", text="Orders with a large subtotal qualify for free shipping.",
        section="Shipping", hash=sha256("y"),
    )
    assert score_pair(with_number, fee) > score_pair(without, fee)


def test_numbers_are_normalised():
    assert numbers_in("500") == numbers_in("500.0") == numbers_in("500.00")


def test_tokenizer_bridges_spec_and_code_wording():
    """A spec says 'reserved'; the code says 'reserve'. They must meet."""
    assert tokenize("reserved") & tokenize("reserve")
    assert tokenize("qualifies") & tokenize("qualify")
    assert tokenize("free_shipping") >= {"free", "shipping"}
    assert tokenize("FreeShipping") >= {"free", "shipping"}


def test_floor_produces_no_candidates(fixture_repo):
    root = fixture_repo()
    chunks = index_repo(root)
    unrelated = Rule(
        id="R-Z", text="Kubernetes pods drain gracefully during node cordon.",
        section="Ops", hash=sha256("z"),
    )
    assert LexicalRetriever(3, 0.15).rank(unrelated, chunks) == []


def test_ranking_is_deterministic(fixture_repo):
    root = fixture_repo()
    chunks = index_repo(root)
    rule = rules_of(root)["R-009"]
    a = [c.chunk.id for c in LexicalRetriever(3, 0.15).rank(rule, chunks)]
    b = [c.chunk.id for c in LexicalRetriever(3, 0.15).rank(rule, list(reversed(chunks)))]
    assert a == b
