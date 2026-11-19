"""CLI: python -m scraper.run --pages N

Collects books from books.toscrape.com and writes:
  data/latest.json, data/history/YYYY-MM-DD.json, data/latest.xlsx, data/changes.json
"""

from __future__ import annotations

import argparse
import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill

from scraper.parse import (
    diff_snapshots,
    parse_categories,
    parse_listing,
    parse_total_pages,
)

BASE = "https://books.toscrape.com/"
CATALOGUE = BASE + "catalogue/page-{n}.html"
USER_AGENT = "price-monitor-study/1.0"
DELAY = 0.5
RETRIES = 3

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
HISTORY = DATA / "history"

log = logging.getLogger("scraper")


class Fetcher:
    """httpx client with a fixed delay between requests and retries."""

    def __init__(self, delay: float = DELAY, retries: int = RETRIES):
        self.delay = delay
        self.retries = retries
        self.client = httpx.Client(
            headers={"User-Agent": USER_AGENT},
            timeout=20,
            follow_redirects=True,
        )
        self._last = 0.0
        self.requests = 0

    def get(self, url: str) -> str:
        for attempt in range(1, self.retries + 1):
            wait = self.delay - (time.monotonic() - self._last)
            if wait > 0:
                time.sleep(wait)
            self._last = time.monotonic()
            self.requests += 1
            try:
                r = self.client.get(url)
                r.raise_for_status()
                # the site sends no charset; the pages are UTF-8
                return r.content.decode("utf-8")
            except (httpx.HTTPError, UnicodeDecodeError) as e:
                log.warning("попытка %d/%d %s: %s", attempt, self.retries, url, e)
                if attempt == self.retries:
                    raise
                time.sleep(2 * attempt)
        raise RuntimeError("unreachable")

    def close(self):
        self.client.close()


def category_map(f: Fetcher) -> dict[str, str]:
    """book url -> category, built from the ~50 category listings.

    Cheaper than opening 1000 detail pages: about 70 requests in total.
    """
    cats = parse_categories(f.get(BASE + "index.html"), BASE + "index.html")
    out: dict[str, str] = {}
    for name, url in cats.items():
        page_url = url
        html = f.get(page_url)
        pages = parse_total_pages(html)
        for n in range(1, pages + 1):
            if n > 1:
                page_url = url.replace("index.html", f"page-{n}.html")
                html = f.get(page_url)
            for b in parse_listing(html, page_url):
                out[b["url"]] = name
    log.info("категорий: %d, книг в них: %d", len(cats), len(out))
    return out


def scrape(pages: int | None, with_categories: bool = True) -> list[dict]:
    f = Fetcher()
    try:
        first = f.get(CATALOGUE.format(n=1))
        total = parse_total_pages(first)
        pages = min(pages or total, total)
        books = parse_listing(first, CATALOGUE.format(n=1))
        log.info("страница 1/%d: %d книг", pages, len(books))
        for n in range(2, pages + 1):
            url = CATALOGUE.format(n=n)
            got = parse_listing(f.get(url), url)
            books.extend(got)
            log.info("страница %d/%d: %d книг", n, pages, len(got))
        if with_categories:
            cmap = category_map(f)
            for b in books:
                b["category"] = cmap.get(b["url"])
        log.info("запросов к сайту: %d", f.requests)
    finally:
        f.close()
    return books


def previous_snapshot(today: str) -> tuple[str | None, list[dict]]:
    files = sorted(p for p in HISTORY.glob("*.json") if p.stem < today)
    if not files:
        return None, []
    last = files[-1]
    return last.stem, json.loads(last.read_text(encoding="utf-8"))["items"]


def write_xlsx(books: list[dict], path: Path, scraped_at: str):
    wb = Workbook()
    ws = wb.active
    ws.title = "Книги"
    head = ["Название", "Цена, £", "Рейтинг", "Наличие", "Категория", "Ссылка"]
    ws.append(head)
    for c in ws[1]:
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor="1E7D45")
    for b in books:
        ws.append(
            [
                b["title"],
                b["price"],
                b["rating"],
                b["availability"],
                b.get("category") or "",
                b["url"],
            ]
        )
    for col, width in zip("ABCDEF", (60, 10, 9, 14, 20, 70)):
        ws.column_dimensions[col].width = width
    for row in ws.iter_rows(min_row=2, min_col=2, max_col=2):
        row[0].number_format = "0.00"
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions
    info = wb.create_sheet("О выгрузке")
    info.append(["Источник", BASE])
    info.append(["Собрано (UTC)", scraped_at])
    info.append(["Книг", len(books)])
    wb.save(path)


def main(argv: list[str] | None = None):
    ap = argparse.ArgumentParser(description="Мониторинг цен books.toscrape.com")
    ap.add_argument("--pages", type=int, default=None, help="сколько страниц каталога (по умолчанию все 50)")
    ap.add_argument("--no-categories", action="store_true", help="не собирать категории (~70 запросов экономии)")
    args = ap.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(message)s", datefmt="%H:%M:%S")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    now = datetime.now(timezone.utc)
    scraped_at = now.isoformat(timespec="seconds")
    today = now.strftime("%Y-%m-%d")

    books = scrape(args.pages, with_categories=not args.no_categories)
    books.sort(key=lambda b: b["title"].lower())

    HISTORY.mkdir(parents=True, exist_ok=True)
    snapshot = {"scraped_at": scraped_at, "source": BASE, "count": len(books), "items": books}
    dump = lambda obj: json.dumps(obj, ensure_ascii=False, indent=1)  # noqa: E731

    (DATA / "latest.json").write_text(dump(snapshot), encoding="utf-8")
    (HISTORY / f"{today}.json").write_text(dump(snapshot), encoding="utf-8")
    write_xlsx(books, DATA / "latest.xlsx", scraped_at)

    prev_date, prev = previous_snapshot(today)
    diff = diff_snapshots(prev, books) if prev_date else {"added": [], "removed": [], "price_changes": []}
    changes = {
        "scraped_at": scraped_at,
        "compared_with": prev_date,
        "first_run": prev_date is None,
        **diff,
    }
    (DATA / "changes.json").write_text(dump(changes), encoding="utf-8")

    log.info(
        "готово: %d книг; сравнение с %s: +%d, -%d, цена изменилась у %d",
        len(books),
        prev_date or "— (первый запуск)",
        len(diff["added"]),
        len(diff["removed"]),
        len(diff["price_changes"]),
    )


if __name__ == "__main__":
    main()
