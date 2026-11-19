from pathlib import Path

import pytest

from scraper.parse import (
    diff_snapshots,
    parse_categories,
    parse_detail,
    parse_listing,
    parse_next_page,
    parse_price,
    parse_rating,
    parse_total_pages,
)

FIX = Path(__file__).parent / "fixtures"
PAGE_URL = "https://books.toscrape.com/catalogue/page-1.html"


@pytest.fixture(scope="module")
def listing():
    return (FIX / "listing_page1.html").read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def detail():
    return (FIX / "detail_page.html").read_text(encoding="utf-8")


def test_parse_price():
    assert parse_price("£51.77") == 51.77
    assert parse_price("Â£ 1,020.50") == 1020.50
    with pytest.raises(ValueError):
        parse_price("нет цены")


def test_parse_rating():
    assert parse_rating(["star-rating", "Three"]) == 3
    assert parse_rating(["star-rating", "Five"]) == 5
    assert parse_rating(["star-rating"]) is None


def test_listing_has_20_books(listing):
    books = parse_listing(listing, PAGE_URL)
    assert len(books) == 20


def test_listing_first_book(listing):
    b = parse_listing(listing, PAGE_URL)[0]
    assert b["title"] == "A Light in the Attic"
    assert b["price"] == 51.77
    assert b["rating"] == 3
    assert b["in_stock"] is True
    assert b["availability"] == "In stock"
    assert b["url"] == "https://books.toscrape.com/catalogue/a-light-in-the-attic_1000/index.html"


def test_listing_full_title_not_truncated(listing):
    titles = [b["title"] for b in parse_listing(listing, PAGE_URL)]
    assert not any(t.endswith("...") for t in titles)


def test_pagination(listing):
    assert parse_next_page(listing, PAGE_URL) == "https://books.toscrape.com/catalogue/page-2.html"
    assert parse_total_pages(listing) == 50
    assert parse_total_pages("<html></html>") == 1


def test_categories(listing):
    cats = parse_categories(listing, PAGE_URL)
    assert "Books" not in cats
    assert cats["Poetry"] == "https://books.toscrape.com/catalogue/category/books/poetry_23/index.html"
    assert len(cats) == 50


def test_detail(detail):
    d = parse_detail(detail)
    assert d["category"] == "Poetry"
    assert d["stock"] == 22


def test_diff_snapshots():
    old = [
        {"url": "a", "title": "A", "price": 10.0},
        {"url": "b", "title": "B", "price": 20.0},
    ]
    new = [
        {"url": "a", "title": "A", "price": 8.5},
        {"url": "c", "title": "C", "price": 5.0},
    ]
    d = diff_snapshots(old, new)
    assert [b["url"] for b in d["added"]] == ["c"]
    assert [b["url"] for b in d["removed"]] == ["b"]
    assert d["price_changes"] == [
        {"title": "A", "url": "a", "old_price": 10.0, "new_price": 8.5, "delta": -1.5}
    ]


def test_diff_no_changes():
    snap = [{"url": "a", "title": "A", "price": 10.0}]
    assert diff_snapshots(snap, snap) == {"added": [], "removed": [], "price_changes": []}
