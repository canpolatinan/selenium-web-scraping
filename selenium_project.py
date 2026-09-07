

import csv
import sqlite3
import logging
import time
import re
import base64
import io
import webbrowser
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import List, Optional

from selenium import webdriver
from selenium.common.exceptions import (
    NoSuchElementException,
    TimeoutException,
    WebDriverException,
)
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

BASE_URL = "https://books.toscrape.com/"
OUTPUT_CSV = "books_data.csv"
OUTPUT_DB = "books_data.db"
OUTPUT_HTML = "books_report.html"
WAIT_TIMEOUT = 10
MAX_PAGES: Optional[int] = None
HEADLESS = True

RATING_MAP = {"One": 1, "Two": 2, "Three": 3, "Four": 4, "Five": 5}

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
    rating: Optional[int]
    page_number: int
    url: str


class DatabaseManager:
    def __init__(self, db_name: str = OUTPUT_DB):
        self.conn = sqlite3.connect(db_name)
        self.cursor = self.conn.cursor()
        self._create_table()

    def _create_table(self):
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS books (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT,
                price REAL,
                stock_status TEXT,
                rating INTEGER,
                page_number INTEGER,
                url TEXT
            )
        """)
        self.conn.commit()

    def insert_books(self, books: List[Book]):
        if not books:
            return
        query = """
            INSERT INTO books (title, price, stock_status, rating, page_number, url)
            VALUES (?, ?, ?, ?, ?, ?)
        """
        data = [(b.title, b.price, b.stock_status, b.rating, b.page_number, b.url) for b in books]
        self.cursor.executemany(query, data)
        self.conn.commit()
        logger.info("%d kitap veritabanına kaydedildi.", len(books))

    def close(self):
        self.conn.close()



class BooksScraper:
    def __init__(self):
        self.driver = self._create_driver()
        self.wait = WebDriverWait(self.driver, WAIT_TIMEOUT)
        self.all_books: List[Book] = []

    def _create_driver(self) -> webdriver.Chrome:
        options = Options()
        if HEADLESS:
            options.add_argument("--headless=new")
        options.add_argument("--window-size=1920,1080")
        options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--log-level=3")
        options.page_load_strategy = "eager"

        driver = webdriver.Chrome(options=options)
        logger.info("Chrome WebDriver başlatıldı (headless=%s).", HEADLESS)
        return driver

    def parse_price(self, price_text: str) -> float:
        match = re.search(r"[\d.]+", price_text)
        return float(match.group()) if match else 0.0

    def retry_action(self, action, retries: int = 3):
        for attempt in range(retries):
            try:
                return action()
            except Exception as e:
                logger.warning("Hata alındı, tekrar deneniyor (%d/%d): %s", attempt + 1, retries, str(e)[:80])
                time.sleep(1)
        return None

    def parse_book_card(self, card_element, page_number: int) -> Optional[Book]:
        try:
            link_element = card_element.find_element(By.CSS_SELECTOR, "h3 a")
            title = link_element.get_attribute("title")
            url = link_element.get_attribute("href")

            raw_price = card_element.find_element(By.CSS_SELECTOR, ".price_color").text.strip()
            price = self.parse_price(raw_price)

            stock_status = card_element.find_element(By.CSS_SELECTOR, ".instock.availability").text.strip()

            rating_classes = card_element.find_element(By.CSS_SELECTOR, "p.star-rating").get_attribute("class")
            rating_word = rating_classes.replace("star-rating", "").strip()
            rating = RATING_MAP.get(rating_word)

            return Book(title, price, stock_status, rating, page_number, url)

        except NoSuchElementException as e:
            logger.error("Kitap ayrıştırma hatası (Sayfa %s): %s", page_number, e)
            return None

    def scrape_current_page(self, page_number: int) -> List[Book]:
        books = []
        try:
            self.wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, ".product_pod")))
        except TimeoutException:
            logger.error("Sayfa %s yüklenemedi.", page_number)
            return books

        cards = self.driver.find_elements(By.CSS_SELECTOR, ".product_pod")
        for card in cards:
            book = self.parse_book_card(card, page_number)
            if book:
                books.append(book)
        return books

    def go_to_next_page(self) -> bool:
        def _click():
            next_button = self.driver.find_element(By.CSS_SELECTOR, "li.next a")
            next_button.click()
            self.wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, ".product_pod")))
            return True

        try:
            self.driver.find_element(By.CSS_SELECTOR, "li.next a")
        except NoSuchElementException:
            return False  # Son sayfa, buton yok

        result = self.retry_action(_click, retries=3)
        return bool(result)

    def export_csv(self):
        if not self.all_books:
            return
        fieldnames = list(asdict(self.all_books[0]).keys())
        with open(OUTPUT_CSV, mode="w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for book in self.all_books:
                writer.writerow(asdict(book))
        logger.info("%d kitap CSV'ye aktarıldı.", len(self.all_books))

    def run(self):
        db_manager = DatabaseManager()
        page_number = 1

        try:
            logger.info("Siteye bağlanılıyor: %s", BASE_URL)
            self.driver.get(BASE_URL)

            while True:
                logger.info("Sayfa %s taranıyor...", page_number)
                page_books = self.scrape_current_page(page_number)

                if page_books:
                    self.all_books.extend(page_books)
                    db_manager.insert_books(page_books)

                if MAX_PAGES and page_number >= MAX_PAGES:
                    break

                if not self.go_to_next_page():
                    logger.info("Tarama tamamlandı. Son sayfaya ulaşıldı.")
                    break

                page_number += 1

        finally:
            self.export_csv()
            db_manager.close()
            self.driver.quit()
            logger.info("Tarayıcı ve veritabanı bağlantısı kapatıldı.")



def _fig_to_base64() -> str:
    """Şu an açık olan matplotlib figürünü base64 PNG'ye çevirir."""
    buf = io.BytesIO()
    plt.savefig(buf, format="png", bbox_inches="tight", dpi=110)
    plt.close()
    buf.seek(0)
    return base64.b64encode(buf.read()).decode("utf-8")


def _make_price_histogram(books: List[Book]) -> str:
    prices = [b.price for b in books]
    plt.figure(figsize=(6, 4))
    plt.hist(prices, bins=15, color="#5b8def", edgecolor="white")
    plt.title("Fiyat Dağılımı")
    plt.xlabel("Fiyat (£)")
    plt.ylabel("Kitap Sayısı")
    plt.tight_layout()
    return _fig_to_base64()


def _make_rating_bar(books: List[Book]) -> str:
    counts = {i: 0 for i in range(1, 6)}
    for b in books:
        if b.rating:
            counts[b.rating] += 1
    plt.figure(figsize=(6, 4))
    plt.bar([str(k) for k in counts.keys()], counts.values(), color="#f0a04b")
    plt.title("Puan Dağılımı (Yıldız)")
    plt.xlabel("Yıldız")
    plt.ylabel("Kitap Sayısı")
    plt.tight_layout()
    return _fig_to_base64()


def generate_html_report(books: List[Book], elapsed: float, filename: str = OUTPUT_HTML) -> Path:
    if not books:
        logger.warning("Rapor için kitap yok, HTML oluşturulmadı.")
        return Path(filename)

    total = len(books)
    in_stock = sum(1 for b in books if "In stock" in b.stock_status)
    avg_price = sum(b.price for b in books) / total
    max_book = max(books, key=lambda b: b.price)
    min_book = min(books, key=lambda b: b.price)
    top_rated = [b for b in books if b.rating == 5][:8]

    price_chart = _make_price_histogram(books)
    rating_chart = _make_rating_bar(books)

    top_books_rows = "".join(
        f"<tr><td>{b.title}</td><td>£{b.price:.2f}</td><td>{'⭐' * (b.rating or 0)}</td>"
        f"<td><a href='{b.url}' target='_blank'>Aç</a></td></tr>"
        for b in sorted(books, key=lambda b: -b.price)[:10]
    )

    html = f"""<!DOCTYPE html>
<html lang="tr">
<head>
<meta charset="UTF-8">
<title>Books Scraper Raporu</title>
<style>
  body {{
    font-family: 'Segoe UI', Arial, sans-serif;
    background: #0f1220;
    color: #eaeaf0;
    margin: 0;
    padding: 40px;
  }}
  h1 {{ font-size: 28px; margin-bottom: 4px; }}
  .subtitle {{ color: #9a9ab0; margin-bottom: 32px; }}
  .cards {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
    gap: 16px;
    margin-bottom: 40px;
  }}
  .card {{
    background: #1a1e33;
    border-radius: 12px;
    padding: 20px;
    border: 1px solid #2b2f4a;
  }}
  .card .label {{ color: #9a9ab0; font-size: 13px; margin-bottom: 6px; }}
  .card .value {{ font-size: 24px; font-weight: 700; color: #5b8def; }}
  .charts {{
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 24px;
    margin-bottom: 40px;
  }}
  .chart-box {{
    background: #1a1e33;
    border-radius: 12px;
    padding: 16px;
    border: 1px solid #2b2f4a;
    text-align: center;
  }}
  .chart-box img {{ max-width: 100%; border-radius: 8px; }}
  table {{
    width: 100%;
    border-collapse: collapse;
    background: #1a1e33;
    border-radius: 12px;
    overflow: hidden;
  }}
  th, td {{
    padding: 12px 16px;
    text-align: left;
    border-bottom: 1px solid #2b2f4a;
    font-size: 14px;
  }}
  th {{ color: #9a9ab0; font-weight: 600; }}
  a {{ color: #5b8def; text-decoration: none; }}
  .section-title {{ font-size: 18px; margin: 32px 0 12px; }}
</style>
</head>
<body>
  <h1>📚 Books to Scrape — Tarama Raporu</h1>
  <div class="subtitle">Tarama {elapsed:.1f} saniye sürdü · {BASE_URL}</div>

  <div class="cards">
    <div class="card"><div class="label">Toplam Kitap</div><div class="value">{total}</div></div>
    <div class="card"><div class="label">Stokta Olan</div><div class="value">{in_stock}</div></div>
    <div class="card"><div class="label">Ortalama Fiyat</div><div class="value">£{avg_price:.2f}</div></div>
    <div class="card"><div class="label">En Pahalı</div><div class="value">£{max_book.price:.2f}</div></div>
    <div class="card"><div class="label">En Ucuz</div><div class="value">£{min_book.price:.2f}</div></div>
  </div>

  <div class="charts">
    <div class="chart-box"><img src="data:image/png;base64,{price_chart}"></div>
    <div class="chart-box"><img src="data:image/png;base64,{rating_chart}"></div>
  </div>

  <div class="section-title">En Pahalı 10 Kitap</div>
  <table>
    <tr><th>Başlık</th><th>Fiyat</th><th>Puan</th><th>Link</th></tr>
    {top_books_rows}
  </table>
</body>
</html>"""

    path = Path(filename)
    path.write_text(html, encoding="utf-8")
    logger.info("HTML rapor oluşturuldu: %s", path.resolve())
    return path


if __name__ == "__main__":
    start_time = time.time()

    scraper = BooksScraper()
    scraper.run()

    elapsed = time.time() - start_time
    logger.info("Tamamlandı: %d kitap toplandı, %.1f saniye sürdü.", len(scraper.all_books), elapsed)

    report_path = generate_html_report(scraper.all_books, elapsed)
    webbrowser.open(f"file://{report_path.resolve()}")