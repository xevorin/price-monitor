"""Pure parsing functions for books.toscrape.com. No network here."""

from __future__ import annotations

import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

RATINGS = {"One": 1, "Two": 2, "Three": 3, "Four": 4, "Five": 5}
_PRICE_RE = re.compile(r"(\d+(?:\.\d+)?)")
_STOCK_RE = re.compile(r"\((\d+) available\)")


def parse_price(text: str) -> float:
    """'£51.77' -> 51.77. Raises ValueError if there is no number."""
    m = _PRICE_RE.search(text.replace(",", ""))
    if not m:
        raise ValueError(f"no price in {text!r}")
    return float(m.group(1))


def parse_rating(classes: list[str]) -> int | None:
    """['star-rating', 'Three'] -> 3."""
    for c in classes:
        if c in RATINGS:
            return RATINGS[c]
    return None


def _clean(text: str) -> str:
    return " ".join(text.split())


def parse_listing(html: str, page_url: str) -> list[dict]:
    """Books from a catalogue or category listing page."""
    soup = BeautifulSoup(html, "html.parser")
    books = []
    for pod in soup.select("article.product_pod"):
        link = pod.select_one("h3 a")
        rating_el = pod.select_one("p.star-rating")
        avail_el = pod.select_one("p.availability")
        books.append(
            {
                "title": link["title"].strip(),
                "price": parse_price(pod.select_one("p.price_color").get_text()),
                "availability": _clean(avail_el.get_text()) if avail_el else "",
                "in_stock": bool(avail_el and "instock" in avail_el.get("class", [])),
                "rating": parse_rating(rating_el.get("class", [])) if rating_el else None,
                "url": urljoin(page_url, link["href"]),
            }
        )
    return books


def parse_next_page(html: str, page_url: str) -> str | None:
    """Absolute URL of the next listing page, or None on the last one."""
    soup = BeautifulSoup(html, "html.parser")
    a = soup.select_one("li.next a")
    return urljoin(page_url, a["href"]) if a else None


def parse_total_pages(html: str) -> int:
    """'Page 1 of 50' -> 50. A listing without a pager has 1 page."""
    soup = BeautifulSoup(html, "html.parser")
    cur = soup.select_one("li.current")
    if not cur:
        return 1
    m = re.search(r"of\s+(\d+)", cur.get_text())
    return int(m.group(1)) if m else 1


def parse_categories(html: str, page_url: str) -> dict[str, str]:
    """Sidebar categories: {name: absolute url}, without the 'Books' root."""
    soup = BeautifulSoup(html, "html.parser")
    out = {}
    for a in soup.select("div.side_categories ul li ul li a"):
        out[_clean(a.get_text())] = urljoin(page_url, a["href"])
    return out


def parse_detail(html: str) -> dict:
    """Category and exact stock count from a book's detail page."""
    soup = BeautifulSoup(html, "html.parser")
    crumbs = soup.select("ul.breadcrumb li a")
    category = _clean(crumbs[-1].get_text()) if len(crumbs) >= 3 else None
    avail_el = soup.select_one("p.availability")
    stock = None
    if avail_el:
        m = _STOCK_RE.search(avail_el.get_text())
        stock = int(m.group(1)) if m else None
    return {"category": category, "stock": stock}


def diff_snapshots(old: list[dict], new: list[dict]) -> dict:
    """Compare two snapshots by url: added, removed and price changes."""
    old_by = {b["url"]: b for b in old}
    new_by = {b["url"]: b for b in new}
    added = [new_by[u] for u in new_by if u not in old_by]
    removed = [old_by[u] for u in old_by if u not in new_by]
    changed = []
    for u, b in new_by.items():
        if u in old_by and old_by[u]["price"] != b["price"]:
            delta = round(b["price"] - old_by[u]["price"], 2)
            changed.append(
                {
                    "title": b["title"],
                    "url": u,
                    "old_price": old_by[u]["price"],
                    "new_price": b["price"],
                    "delta": delta,
                }
            )
    changed.sort(key=lambda c: abs(c["delta"]), reverse=True)
    return {"added": added, "removed": removed, "price_changes": changed}
