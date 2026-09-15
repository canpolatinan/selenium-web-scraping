

import argparse
import csv
import json
import logging
import re
import sqlite3
import time
import webbrowser

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

BASE_URL = "https://books.toscrape.com/"
CATALOGUE_PAGE_URL = (
    "https://books.toscrape.com/catalogue/page-{n}.html"
)

RATING_MAP = {
    "One": 1,
    "Two": 2,
    "Three": 3,
    "Four": 4,
    "Five": 5,
}

STOCK_COUNT_RE = re.compile(r"\((\d+)\s+available\)")
PRICE_RE = re.compile(r"[\d.]+")

USER_AGENT = (
    "Mozilla/5.0 (compatible; BookScope/1.0; +educational-use)"
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)

logger = logging.getLogger(__name__)



@dataclass
class Book:
    title: str
    price: float
    stock_status: str
    stock_count: Optional[int]
    rating: Optional[int]
    category: Optional[str]
    page_number: int
    url: str




def make_session() -> requests.Session:
    session = requests.Session()

    session.headers.update({
        "User-Agent": USER_AGENT
    })

    retry = Retry(
        total=4,
        backoff_factor=0.5,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
    )

    adapter = HTTPAdapter(
        max_retries=retry,
        pool_maxsize=20
    )

    session.mount("https://", adapter)
    session.mount("http://", adapter)

    return session

def parse_price(price_text: str) -> float:
    match = PRICE_RE.search(price_text)
    return float(match.group()) if match else 0.0


def parse_stock_count(stock_text: str) -> Optional[int]:
    match = STOCK_COUNT_RE.search(stock_text)
    return int(match.group(1)) if match else None


def get_total_pages(soup: BeautifulSoup) -> int:
    current = soup.select_one(".current")

    if not current:
        return 1

    match = re.search(
        r"of\s+(\d+)",
        current.get_text(strip=True)
    )

    return int(match.group(1)) if match else 1


def parse_listing_page(
    html: str,
    page_number: int
) -> List[Book]:

    soup = BeautifulSoup(html, "lxml")
    books = []

    for card in soup.select(".product_pod"):
        try:
            link = card.select_one("h3 a")

            title = link.get("title", "").strip()

            url = requests.compat.urljoin(
                BASE_URL,
                link.get("href")
            )

            raw_price = card.select_one(
                ".price_color"
            ).get_text(strip=True)

            price = parse_price(raw_price)

            stock_text = card.select_one(
                ".instock.availability"
            ).get_text(strip=True)

            rating_classes = card.select_one(
                "p.star-rating"
            ).get("class", [])

            rating_word = next(
                (
                    c for c in rating_classes
                    if c != "star-rating"
                ),
                None
            )

            rating = (
                RATING_MAP.get(rating_word)
                if rating_word
                else None
            )

            books.append(
                Book(
                    title=title,
                    price=price,
                    stock_status=stock_text,
                    stock_count=parse_stock_count(stock_text),
                    rating=rating,
                    category=None,
                    page_number=page_number,
                    url=url,
                )
            )

        except AttributeError as e:
            logger.error(
                "Kitap ayrıştırma hatası "
                "(Sayfa %s): %s",
                page_number,
                e
            )

    return books


def parse_book_detail(
    html: str
) -> Tuple[Optional[str], Optional[int]]:

    soup = BeautifulSoup(html, "lxml")

    breadcrumb = soup.select(
        "ul.breadcrumb li a"
    )

    category = (
        breadcrumb[-1].get_text(strip=True)
        if len(breadcrumb) >= 3
        else None
    )

    availability = soup.select_one(
        "#product_description ~ "
        "p.instock.availability"
    )

    if availability is None:
        availability = soup.select_one(
            "p.instock.availability"
        )

    stock_count = (
        parse_stock_count(
            availability.get_text(strip=True)
        )
        if availability
        else None
    )

    return category, stock_count

class SeleniumDetailScraper:

    def __init__(
        self,
        headless: bool = True,
        screenshot_dir: Path = Path("screenshots")
    ):

        self.screenshot_dir = screenshot_dir
        self.screenshot_dir.mkdir(
            parents=True,
            exist_ok=True
        )

        options = Options()

        if headless:
            options.add_argument("--headless")

        options.add_argument("--window-size=1920,1080")
        options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")

        self.driver = webdriver.Chrome(
            options=options
        )

        self.wait = WebDriverWait(
            self.driver,
            10
        )

    def scrape_book_detail(
        self,
        url: str,
        index: int
    ) -> Tuple[Optional[str], Optional[int]]:

        try:
            self.driver.get(url)

            breadcrumb = self.wait.until(
                EC.presence_of_all_elements_located(
                    (
                        By.CSS_SELECTOR,
                        "ul.breadcrumb li a"
                    )
                )
            )

            category = (
                breadcrumb[-1].text.strip()
                if len(breadcrumb) >= 3
                else None
            )

            availability = self.driver.find_element(
                By.CSS_SELECTOR,
                "p.instock.availability"
            )

            stock_text = availability.text.strip()

            stock_count = parse_stock_count(
                stock_text
            )

            return category, stock_count

        except Exception as e:

            logger.error(
                "Selenium detay hatası (%s): %s",
                url,
                e
            )

            try:
                self.driver.save_screenshot(
                    str(
                        self.screenshot_dir
                        / f"error_{index}.png"
                    )
                )
            except Exception:
                pass

            return None, None

    def close(self):
        self.driver.quit()

class BooksScraper:

    def __init__(
        self,
        max_pages: Optional[int] = None,
        workers: int = 10,
        with_details: bool = False,
        engine: str = "hybrid"
    ):

        self.max_pages = max_pages
        self.workers = workers
        self.with_details = with_details
        self.engine = engine

        self.session = make_session()

        self.all_books: List[Book] = []
        self.seen_urls: Set[str] = set()

    def _fetch(self, url: str) -> Optional[str]:

        try:
            response = self.session.get(
                url,
                timeout=10
            )

            response.raise_for_status()

            return response.text

        except requests.RequestException as e:

            logger.error(
                "İstek başarısız (%s): %s",
                url,
                e
            )

            return None

    def run(self) -> List[Book]:

        start_time = time.time()

        first_html = self._fetch(BASE_URL)

        if not first_html:

            logger.error(
                "İlk sayfa alınamadı."
            )

            return []

        soup = BeautifulSoup(
            first_html,
            "lxml"
        )

        total_pages = get_total_pages(soup)

        if self.max_pages:
            total_pages = min(
                total_pages,
                self.max_pages
            )

        logger.info(
            "Toplam %d sayfa taranacak "
            "(%d paralel işçi ile).",
            total_pages,
            self.workers
        )

        page_urls = {
            1: BASE_URL
        }

        for n in range(2, total_pages + 1):
            page_urls[n] = CATALOGUE_PAGE_URL.format(
                n=n
            )

        results: Dict[int, str] = {}

        with ThreadPoolExecutor(
            max_workers=self.workers
        ) as executor:

            futures = {
                executor.submit(
                    self._fetch,
                    url
                ): page

                for page, url in page_urls.items()
            }

            for future in as_completed(futures):

                page = futures[future]
                html = future.result()

                if html:
                    results[page] = html

        for page in sorted(results):

            books = parse_listing_page(
                results[page],
                page
            )

            for book in books:

                if book.url in self.seen_urls:
                    continue

                self.seen_urls.add(book.url)
                self.all_books.append(book)

        logger.info(
            "%d sayfa tarandı, %d kitap toplandı.",
            len(results),
            len(self.all_books)
        )

        if self.with_details and self.all_books:

            if self.engine == "hybrid":

                self._enrich_with_selenium()

            else:

                self._enrich_with_requests()

        elapsed = time.time() - start_time

        logger.info(
            "Tarama tamamlandı: %d kitap, %.1f saniye.",
            len(self.all_books),
            elapsed
        )

        return self.all_books

    def _enrich_with_requests(self):

        logger.info(
            "Requests detay taraması başlıyor..."
        )

        with ThreadPoolExecutor(
            max_workers=self.workers
        ) as executor:

            futures = {
                executor.submit(
                    self._fetch,
                    book.url
                ): book

                for book in self.all_books
            }

            done = 0

            for future in as_completed(futures):

                book = futures[future]
                html = future.result()

                if html:

                    category, stock_count = (
                        parse_book_detail(html)
                    )

                    book.category = category

                    if stock_count is not None:
                        book.stock_count = stock_count

                done += 1

                if done % 100 == 0:

                    logger.info(
                        "Requests detay: %d/%d",
                        done,
                        len(self.all_books)
                    )

    def _enrich_with_selenium(self):

        logger.info(
            "Selenium detay taraması başlıyor..."
        )

        selenium_scraper = SeleniumDetailScraper()

        try:

            for index, book in enumerate(
                self.all_books,
                start=1
            ):

                category, stock_count = (
                    selenium_scraper.scrape_book_detail(
                        book.url,
                        index
                    )
                )

                book.category = category

                if stock_count is not None:
                    book.stock_count = stock_count

                if index % 50 == 0:

                    logger.info(
                        "Selenium detay: %d/%d",
                        index,
                        len(self.all_books)
                    )

        finally:

            selenium_scraper.close()

class DatabaseManager:

    def __init__(self, db_path: Path):

        self.conn = sqlite3.connect(
            db_path
        )

        self.cursor = self.conn.cursor()

        self._create_tables()

    def _create_tables(self):

        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS books (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT,
                price REAL,
                stock_status TEXT,
                stock_count INTEGER,
                rating INTEGER,
                category TEXT,
                page_number INTEGER,
                url TEXT UNIQUE,
                updated_at TEXT
            )
        """)

        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS price_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                book_url TEXT,
                price REAL,
                checked_at TEXT
            )
        """)

        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS stock_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                book_url TEXT,
                stock_count INTEGER,
                checked_at TEXT
            )
        """)

        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS scan_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                started_at TEXT,
                total_books INTEGER,
                duration_seconds REAL
            )
        """)

        self.conn.commit()

        self._migrate_schema()

    def _migrate_schema(self):

        expected_columns = {
            "stock_count": "INTEGER",
            "category": "TEXT",
            "updated_at": "TEXT",
        }

        self.cursor.execute(
            "PRAGMA table_info(books)"
        )

        existing_columns = {
            row[1]
            for row in self.cursor.fetchall()
        }

        for column, col_type in expected_columns.items():

            if column not in existing_columns:

                logger.warning(
                    "Eksik sütun ekleniyor: %s",
                    column
                )

                self.cursor.execute(
                    f"ALTER TABLE books "
                    f"ADD COLUMN {column} {col_type}"
                )

        self.cursor.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS
            idx_books_url ON books(url)
        """)

        self.conn.commit()

    def insert_books(
        self,
        books: List[Book],
        elapsed: float
    ) -> int:

        if not books:
            return 0

        now = datetime.now().isoformat(
            timespec="seconds"
        )

        inserted = 0

        for book in books:

            self.cursor.execute(
                "SELECT price, stock_count "
                "FROM books WHERE url = ?",
                (book.url,)
            )

            previous = self.cursor.fetchone()

            self.cursor.execute("""
                INSERT INTO books (
                    title,
                    price,
                    stock_status,
                    stock_count,
                    rating,
                    category,
                    page_number,
                    url,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(url) DO UPDATE SET
                    title = excluded.title,
                    price = excluded.price,
                    stock_status = excluded.stock_status,
                    stock_count = excluded.stock_count,
                    rating = excluded.rating,
                    category = excluded.category,
                    page_number = excluded.page_number,
                    updated_at = excluded.updated_at
            """, (
                book.title,
                book.price,
                book.stock_status,
                book.stock_count,
                book.rating,
                book.category,
                book.page_number,
                book.url,
                now
            ))

            if previous is None:
                inserted += 1
            self.cursor.execute("""
                INSERT INTO price_history (
                    book_url,
                    price,
                    checked_at
                )
                VALUES (?, ?, ?)
            """, (
                book.url,
                book.price,
                now
            ))
            self.cursor.execute("""
                INSERT INTO stock_history (
                    book_url,
                    stock_count,
                    checked_at
                )
                VALUES (?, ?, ?)
            """, (
                book.url,
                book.stock_count,
                now
            ))

        self.cursor.execute("""
            INSERT INTO scan_runs (
                started_at,
                total_books,
                duration_seconds
            )
            VALUES (?, ?, ?)
        """, (
            now,
            len(books),
            elapsed
        ))

        self.conn.commit()

        logger.info(
            "%d yeni kitap kaydedildi.",
            inserted
        )

        logger.info(
            "Fiyat ve stok geçmişi güncellendi."
        )

        return inserted

    def close(self):
        self.conn.close()

def export_csv(
    books: List[Book],
    path: Path
):

    if not books:
        return

    fieldnames = list(
        asdict(books[0]).keys()
    )

    with open(
        path,
        mode="w",
        newline="",
        encoding="utf-8"
    ) as f:

        writer = csv.DictWriter(
            f,
            fieldnames=fieldnames
        )

        writer.writeheader()

        for book in books:
            writer.writerow(
                asdict(book)
            )

    logger.info(
        "CSV oluşturuldu: %s",
        path
    )


def export_json(
    books: List[Book],
    path: Path
):

    if not books:
        return

    with open(
        path,
        mode="w",
        encoding="utf-8"
    ) as f:

        json.dump(
            [asdict(b) for b in books],
            f,
            ensure_ascii=False,
            indent=2
        )

    logger.info(
        "JSON oluşturuldu: %s",
        path
    )

PALETTE = {
    "paper": "#F3ECD9",
    "paper_dark": "#E8DDC0",
    "ink": "#2B2118",
    "ink_muted": "#6B5D4F",
    "burgundy": "#7A2E2E",
    "forest": "#4B5D45",
    "gold": "#B08D57",
    "line": "#D8CBA8",
}


def _apply_chart_style():

    plt.rcParams.update({
        "font.family": "DejaVu Sans",
        "text.color": PALETTE["ink"],
        "axes.edgecolor": PALETTE["line"],
        "axes.labelcolor": PALETTE["ink_muted"],
        "xtick.color": PALETTE["ink_muted"],
        "ytick.color": PALETTE["ink_muted"],
        "figure.facecolor": PALETTE["paper_dark"],
        "axes.facecolor": PALETTE["paper_dark"],
        "savefig.facecolor": PALETTE["paper_dark"],
    })


def _fig_to_base64() -> str:

    import base64
    import io

    buffer = io.BytesIO()

    plt.savefig(
        buffer,
        format="png",
        bbox_inches="tight",
        dpi=130
    )

    plt.close()

    buffer.seek(0)

    return base64.b64encode(
        buffer.read()
    ).decode("utf-8")


def _make_price_histogram(
    books: List[Book]
) -> str:

    prices = [b.price for b in books]

    plt.figure(figsize=(5, 3.6))

    plt.hist(
        prices,
        bins=15,
        color=PALETTE["burgundy"],
        edgecolor=PALETTE["paper"]
    )

    plt.xlabel("Fiyat (£)")
    plt.ylabel("Kitap sayısı")

    for spine in ["top", "right"]:
        plt.gca().spines[spine].set_visible(False)

    plt.tight_layout()

    return _fig_to_base64()


def _make_rating_bar(
    books: List[Book]
) -> str:

    counts = {
        i: 0
        for i in range(1, 6)
    }

    for book in books:

        if book.rating:
            counts[book.rating] += 1

    plt.figure(figsize=(5, 3.6))

    plt.bar(
        [str(k) for k in counts.keys()],
        counts.values(),
        color=PALETTE["forest"],
        edgecolor=PALETTE["paper"]
    )

    plt.xlabel("Yıldız")
    plt.ylabel("Kitap sayısı")

    for spine in ["top", "right"]:
        plt.gca().spines[spine].set_visible(False)

    plt.tight_layout()

    return _fig_to_base64()


def _make_stock_pie(
    books: List[Book]
) -> str:

    in_stock = sum(
        1 for b in books
        if "In stock" in b.stock_status
    )

    out_stock = len(books) - in_stock

    plt.figure(figsize=(5, 3.6))

    values = (
        [in_stock, out_stock]
        if out_stock
        else [in_stock]
    )

    labels = (
        ["Stokta", "Stok yok"]
        if out_stock
        else ["Stokta"]
    )

    plt.pie(
        values,
        labels=labels,
        autopct="%1.0f%%",
        colors=[
            PALETTE["gold"],
            PALETTE["ink_muted"]
        ][:len(values)],
        wedgeprops={
            "edgecolor": PALETTE["paper_dark"],
            "linewidth": 2
        },
        textprops={
            "color": PALETTE["ink"]
        }
    )

    plt.tight_layout()

    return _fig_to_base64()


def _category_breakdown_rows(
    books: List[Book]
) -> str:

    counts: Dict[str, int] = {}

    for book in books:

        if book.category:

            counts[book.category] = (
                counts.get(book.category, 0) + 1
            )

    if not counts:
        return ""

    top = sorted(
        counts.items(),
        key=lambda kv: -kv[1]
    )[:8]

    max_count = top[0][1]

    rows = ""

    for name, count in top:

        width_pct = int(
            count / max_count * 100
        )

        rows += f"""
        <div class="cat-row">
          <span class="cat-name">{name}</span>
          <div class="cat-track">
            <div class="cat-fill"
                 style="width:{width_pct}%">
            </div>
          </div>
          <span class="cat-count">{count}</span>
        </div>
        """

    return rows


def generate_html_report(
    books: List[Book],
    elapsed: float,
    output_path: Path,
    engine: str
) -> Path:

    if not books:

        logger.warning(
            "Kitap yok, HTML oluşturulmadı."
        )

        return output_path

    _apply_chart_style()

    total = len(books)

    in_stock = sum(
        1 for b in books
        if "In stock" in b.stock_status
    )

    avg_price = sum(
        b.price for b in books
    ) / total

    max_book = max(
        books,
        key=lambda b: b.price
    )

    min_book = min(
        books,
        key=lambda b: b.price
    )

    five_star = sum(
        1 for b in books
        if b.rating == 5
    )

    price_chart = _make_price_histogram(books)
    rating_chart = _make_rating_bar(books)
    stock_chart = _make_stock_pie(books)

    category_rows = _category_breakdown_rows(books)

    top_books_rows = "".join(
        f"""
        <tr>
          <td class="ledger-title">
            {b.title}
          </td>
          <td class="ledger-num">
            £{b.price:.2f}
          </td>
          <td class="ledger-stars">
            {'★' * (b.rating or 0)}
            {'☆' * (5 - (b.rating or 0))}
          </td>
          <td class="ledger-link">
            <a href="{b.url}" target="_blank">
              Açık defter
            </a>
          </td>
        </tr>
        """
        for b in sorted(
            books,
            key=lambda b: -b.price
        )[:10]
    )

    category_section = ""

    if category_rows:

        category_section = f"""
        <section class="panel">
          <h2>En çok kitabın bulunduğu raflar</h2>
          <div class="cat-list">
            {category_rows}
          </div>
        </section>
        """

    html = f"""<!DOCTYPE html>
<html lang="tr">
<head>
<meta charset="UTF-8">
<meta name="viewport"
      content="width=device-width, initial-scale=1">

<title>BookScope — Katalog Raporu</title>

<style>

:root {{
  --paper: {PALETTE['paper']};
  --paper-dark: {PALETTE['paper_dark']};
  --ink: {PALETTE['ink']};
  --ink-muted: {PALETTE['ink_muted']};
  --burgundy: {PALETTE['burgundy']};
  --forest: {PALETTE['forest']};
  --gold: {PALETTE['gold']};
  --line: {PALETTE['line']};
}}

* {{
  box-sizing: border-box;
}}

body {{
  font-family: Georgia, serif;
  background: var(--paper);
  color: var(--ink);
  margin: 0;
  padding: 56px 24px 80px;
  line-height: 1.5;
}}

.sheet {{
  max-width: 980px;
  margin: 0 auto;
}}

.masthead {{
  text-align: center;
  padding-bottom: 28px;
  margin-bottom: 40px;
  border-bottom: 1px solid var(--ink);
}}

.kicker {{
  font-family: Arial, sans-serif;
  font-size: 12px;
  letter-spacing: 0.08em;
  color: var(--ink-muted);
  margin-bottom: 10px;
}}

.masthead h1 {{
  font-size: 42px;
  font-weight: 400;
  margin: 0 0 10px;
}}

.rule {{
  width: 64px;
  height: 1px;
  background: var(--gold);
  margin: 16px auto;
}}

.subtitle {{
  font-family: Arial, sans-serif;
  font-size: 14px;
  color: var(--ink-muted);
}}

.index-row {{
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  border: 1px solid var(--line);
  margin-bottom: 48px;
}}

.index-card {{
  padding: 20px 16px;
  border-right: 1px solid var(--line);
  text-align: center;
}}

.index-card:last-child {{
  border-right: none;
}}

.index-card .tab {{
  font-family: Arial, sans-serif;
  font-size: 11px;
  color: var(--ink-muted);
  margin-bottom: 8px;
}}

.index-card .figure {{
  font-size: 26px;
  color: var(--burgundy);
}}

section.panel {{
  margin-bottom: 48px;
}}

section.panel h2 {{
  font-size: 19px;
  font-weight: 400;
  margin: 0 0 20px;
  padding-bottom: 10px;
  border-bottom: 1px solid var(--line);
}}

.charts {{
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 20px;
}}

.chart-box {{
  background: var(--paper-dark);
  border: 1px solid var(--line);
  padding: 14px;
  text-align: center;
}}

.chart-box img {{
  max-width: 100%;
  display: block;
  margin: 0 auto;
}}

.chart-box .caption {{
  font-family: Arial, sans-serif;
  font-size: 12px;
  color: var(--ink-muted);
  margin-top: 8px;
}}

.cat-list {{
  display: flex;
  flex-direction: column;
  gap: 10px;
}}

.cat-row {{
  display: grid;
  grid-template-columns: 160px 1fr 32px;
  align-items: center;
  gap: 14px;
  font-family: Arial, sans-serif;
  font-size: 13px;
}}

.cat-track {{
  height: 8px;
  background: var(--paper-dark);
  border: 1px solid var(--line);
}}

.cat-fill {{
  height: 100%;
  background: var(--forest);
}}

.cat-count {{
  text-align: right;
  color: var(--ink-muted);
}}

table.ledger {{
  width: 100%;
  border-collapse: collapse;
  font-family: Arial, sans-serif;
  font-size: 14px;
}}

table.ledger th {{
  text-align: left;
  font-weight: 400;
  color: var(--ink-muted);
  font-size: 12px;
  padding: 10px 12px;
  border-bottom: 1px solid var(--ink);
}}

table.ledger td {{
  padding: 12px;
  border-bottom: 1px solid var(--line);
}}

table.ledger tr:nth-child(even) {{
  background: var(--paper-dark);
}}

.ledger-num {{
  color: var(--burgundy);
}}

.ledger-stars {{
  color: var(--gold);
  letter-spacing: 1px;
}}

.ledger-link a {{
  color: var(--forest);
  text-decoration: none;
  border-bottom: 1px dotted var(--forest);
}}

footer {{
  text-align: center;
  margin-top: 56px;
  padding-top: 20px;
  border-top: 1px solid var(--line);
  font-family: Arial, sans-serif;
  font-size: 12px;
  color: var(--ink-muted);
}}

@media (max-width: 720px) {{

  .index-row {{
    grid-template-columns: repeat(2, 1fr);
  }}

  .index-card {{
    border-bottom: 1px solid var(--line);
  }}

  .charts {{
    grid-template-columns: 1fr;
  }}

  .cat-row {{
    grid-template-columns: 100px 1fr 28px;
  }}

}}

</style>
</head>

<body>

<div class="sheet">

  <div class="masthead">

    <div class="kicker">
      BOOKSCOPE // HYBRID SCRAPER
    </div>

    <h1>Books to Scrape</h1>

    <div class="rule"></div>

    <div class="subtitle">
      {total} kitap {elapsed:.1f} saniyede tarandı
      — Engine: {engine}
    </div>

  </div>

  <div class="index-row">

    <div class="index-card">
      <div class="tab">Toplam kitap</div>
      <div class="figure">{total}</div>
    </div>

    <div class="index-card">
      <div class="tab">Stokta</div>
      <div class="figure">{in_stock}</div>
    </div>

    <div class="index-card">
      <div class="tab">Ortalama fiyat</div>
      <div class="figure">£{avg_price:.2f}</div>
    </div>

    <div class="index-card">
      <div class="tab">5 yıldızlı</div>
      <div class="figure">{five_star}</div>
    </div>

    <div class="index-card">
      <div class="tab">En pahalı</div>
      <div class="figure">£{max_book.price:.2f}</div>
    </div>

  </div>

  <section class="panel">

    <h2>Dağılımlar</h2>

    <div class="charts">

      <div class="chart-box">
        <img src="data:image/png;base64,{price_chart}">
        <div class="caption">Fiyat dağılımı</div>
      </div>

      <div class="chart-box">
        <img src="data:image/png;base64,{rating_chart}">
        <div class="caption">Puan dağılımı</div>
      </div>

      <div class="chart-box">
        <img src="data:image/png;base64,{stock_chart}">
        <div class="caption">Stok durumu</div>
      </div>

    </div>

  </section>

  {category_section}

  <section class="panel">

    <h2>En pahalı on kitap</h2>

    <table class="ledger">

      <tr>
        <th>Başlık</th>
        <th>Fiyat</th>
        <th>Puan</th>
        <th>Bağlantı</th>
      </tr>

      {top_books_rows}

    </table>

  </section>

  <footer>
    En ucuz kitap: {min_book.title}
    — £{min_book.price:.2f}
  </footer>

</div>

</body>
</html>
"""

    output_path.write_text(
        html,
        encoding="utf-8"
    )

    logger.info(
        "HTML rapor oluşturuldu: %s",
        output_path.resolve()
    )

    return output_path




def parse_args() -> argparse.Namespace:

    parser = argparse.ArgumentParser(
        description="BookScope — Hybrid Web Scraper"
    )

    parser.add_argument(
        "--max-pages",
        type=int,
        default=None,
        help="Taranacak maksimum sayfa"
    )

    parser.add_argument(
        "--workers",
        type=int,
        default=10,
        help="Paralel requests işçisi"
    )

    parser.add_argument(
        "--with-details",
        action="store_true",
        help="Detay sayfalarını da tara"
    )

    parser.add_argument(
        "--engine",
        choices=["hybrid", "requests"],
        default="hybrid",
        help="Detay tarama motoru"
    )

    parser.add_argument(
        "--output-dir",
        type=str,
        default="output",
        help="Çıktı klasörü"
    )

    parser.add_argument(
        "--no-browser-open",
        action="store_true",
        help="Raporu otomatik açma"
    )

    return parser.parse_args()




def main():

    args = parse_args()

    output_dir = Path(
        args.output_dir
    )

    output_dir.mkdir(
        parents=True,
        exist_ok=True
    )

    start_time = time.time()

    scraper = BooksScraper(
        max_pages=args.max_pages,
        workers=args.workers,
        with_details=args.with_details,
        engine=args.engine
    )

    books = scraper.run()

    elapsed = time.time() - start_time

    if not books:

        logger.error(
            "Hiç kitap toplanamadı."
        )

        return
    db_manager = DatabaseManager(
        output_dir / "books_data.db"
    )

    db_manager.insert_books(
        books,
        elapsed
    )

    db_manager.close()
    export_csv(
        books,
        output_dir / "books_data.csv"
    )

    export_json(
        books,
        output_dir / "books_data.json"
    )
    report_path = generate_html_report(
        books,
        elapsed,
        output_dir / "books_report.html",
        args.engine
    )

    if not args.no_browser_open:

        webbrowser.open(
            f"file://{report_path.resolve()}"
        )

    logger.info(
        "TÜM İŞLEMLER TAMAMLANDI."
    )


if __name__ == "__main__":
    main()