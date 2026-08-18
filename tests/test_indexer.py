from __future__ import annotations

from specguard.indexer import index_file, index_repo, index_repo_verbose, iter_python_files


def test_shipping_chunks_and_line_ranges(fixture_repo):
    root = fixture_repo()
    chunks = index_file(root / "orderflow" / "shipping.py", root)
    by_name = {c.name: c for c in chunks}

    assert set(by_name) == {"shipping_fee", "FREE_SHIPPING_THRESHOLD+STANDARD_SHIPPING_FEE"}

    fee = by_name["shipping_fee"]
    assert fee.kind == "function"
    assert fee.id == "orderflow/shipping.py::shipping_fee"
    assert (fee.line_start, fee.line_end) == (7, 15)
    assert fee.signature == "def shipping_fee(subtotal)"
    assert "500 or more" in (fee.docstring or "")

    consts = by_name["FREE_SHIPPING_THRESHOLD+STANDARD_SHIPPING_FEE"]
    assert consts.kind == "constants"
    assert (consts.line_start, consts.line_end) == (3, 4)


def test_numbered_source_uses_absolute_lines(fixture_repo):
    root = fixture_repo()
    fee = next(
        c for c in index_repo(root) if c.id == "orderflow/shipping.py::shipping_fee"
    )
    first, last = fee.numbered_source().splitlines()[0], fee.numbered_source().splitlines()[-1]
    assert first.startswith("   7 |")
    assert last.startswith("  15 |")


def test_methods_and_classes_are_separate_chunks(fixture_repo):
    ids = {c.id for c in index_repo(fixture_repo())}
    assert "orderflow/inventory.py::Warehouse" in ids
    assert "orderflow/inventory.py::Warehouse.reserve" in ids
    assert "orderflow/inventory.py::Reservation.is_expired" in ids


def test_specguardignore_keeps_tests_out(fixture_repo):
    root = fixture_repo()
    files = {p.relative_to(root).as_posix() for p in iter_python_files(root)}
    assert files == {
        "orderflow/__init__.py",
        "orderflow/checkout.py",
        "orderflow/inventory.py",
        "orderflow/pricing.py",
        "orderflow/shipping.py",
    }


def test_unparseable_file_is_reported_not_swallowed(fixture_repo):
    root = fixture_repo()
    (root / "orderflow" / "broken.py").write_text("def nope(:\n", encoding="utf-8")
    chunks, unreadable, count = index_repo_verbose(root)
    assert unreadable == ["orderflow/broken.py"]
    assert count == 6
    assert chunks  # the rest of the repo is still indexed


def test_chunk_hash_tracks_content(fixture_repo):
    clean = {c.id: c.hash for c in index_repo(fixture_repo("clean"))}
    drifted = {c.id: c.hash for c in index_repo(fixture_repo("drifted"))}
    assert clean["orderflow/shipping.py::shipping_fee"] != drifted["orderflow/shipping.py::shipping_fee"]
    assert clean["orderflow/pricing.py::calculate_tax"] == drifted["orderflow/pricing.py::calculate_tax"]
