from __future__ import annotations

from specguard.spec_parser import normalise, parse_spec


def test_twelve_rules_with_stable_ids(fixture_repo):
    rules = parse_spec(fixture_repo() / "SPEC.md")
    assert len(rules) == 12
    assert [r.id for r in rules] == [f"R-{n:03d}" for n in range(1, 13)]


def test_ids_are_stable_across_reparses(fixture_repo):
    root = fixture_repo()
    first = parse_spec(root / "SPEC.md")
    second = parse_spec(root / "SPEC.md")
    assert [(r.id, r.hash) for r in first] == [(r.id, r.hash) for r in second]


def test_sections_are_captured(fixture_repo):
    rules = {r.id: r for r in parse_spec(fixture_repo() / "SPEC.md")}
    assert rules["R-001"].section == "Pricing"
    assert rules["R-004"].section == "Shipping"
    assert rules["R-008"].section == "Checkout"


def test_r012_is_flagged_unverifiable(fixture_repo):
    rules = {r.id: r for r in parse_spec(fixture_repo() / "SPEC.md")}
    r012 = rules["R-012"]
    assert r012.unverifiable is True
    assert "fast" in (r012.reason or "")
    # Rejected, not dropped: the panel asks "what if the spec is vague?"
    assert r012.text == "The checkout should feel fast for the user."


def test_only_r012_is_unverifiable(fixture_repo):
    rules = parse_spec(fixture_repo() / "SPEC.md")
    assert [r.id for r in rules if r.unverifiable] == ["R-012"]


def test_vague_wording_with_a_predicate_is_kept(tmp_path):
    spec = tmp_path / "SPEC.md"
    spec.write_text(
        "## Rules\n\n### Perf\n\n"
        "- The response must be fast, meaning under 200 ms.\n"
        "- The system should be robust.\n",
        encoding="utf-8",
    )
    rules = parse_spec(spec)
    assert rules[0].unverifiable is False  # "200 ms" is a measurable predicate
    assert rules[1].unverifiable is True


def test_hash_ignores_whitespace_and_case():
    assert normalise("  Free   SHIPPING at 500 ") == "free shipping at 500"
