# BookScope

Python ile yazılmış hibrit bir web scraper. [Books to Scrape](https://books.toscrape.com/) (scraping pratiği için hazırlanmış örnek bir kitap sitesi) kataloğunu tarar, verileri SQLite veritabanına kaydeder, fiyat ve stok geçmişini tutar ve CSV, JSON ile HTML rapor üretir.

## Nasıl çalışır

Katalog liste sayfaları `requests` ve `ThreadPoolExecutor` ile paralel çekilir. `--with-details` verilirse her kitabın detay sayfası da ziyaret edilir (kategori ve stok adedi için). `hybrid` motorda bu adım Selenium (headless Chrome) ile, `requests` motorunda paralel HTTP istekleriyle yapılır.

## Özellikler

- **Paralel tarama:** Tekrar denemeli (429 ve 5xx hatalarında) HTTP oturumu, ayarlanabilir işçi sayısı.
- **İki motor:** `hybrid` (detaylar Selenium ile) ve `requests` (detaylar paralel HTTP ile).
- **SQLite kaydı:** Kitaplar URL üzerinden `INSERT ... ON CONFLICT DO UPDATE` ile güncellenir. Her taramada fiyat ve stok geçmişi ayrı tablolara eklenir. Eksik sütunlar `PRAGMA table_info` ile kontrol edilip otomatik eklenir.
- **Çıktılar:** CSV, JSON ve tek dosyalık HTML rapor. Raporda `matplotlib` ile üretilip base64 olarak gömülen fiyat, puan ve stok grafikleri, en pahalı 10 kitap ve (detay taraması yapıldıysa) kategori dağılımı bulunur.
- **Hata kaydı:** Selenium detay taramasında bir sayfa başarısız olursa `screenshots/error_N.png` olarak ekran görüntüsü alınır.

## Kurulum

Gereksinimler: Python 3 ve (yalnızca `hybrid` motorda detay taraması için) Google Chrome. Selenium 4.6 ve üzeri sürücüyü kendisi indirir.

```bash
git clone https://github.com/canpolatinan/selenium-web-scraping.git
cd selenium-web-scraping
python -m venv .venv
# Windows:      .venv\Scripts\activate
# macOS/Linux:  source .venv/bin/activate
pip install -r requirements.txt
```

## Kullanım

```bash
# Hızlı deneme: ilk 5 sayfa, raporu tarayıcıda açma
python selenium_project.py --max-pages 5 --no-browser-open

# Detay sayfalarını da tara (hybrid motor, Selenium kullanır)
python selenium_project.py --with-details --max-pages 3

# Detayları Selenium yerine paralel HTTP istekleriyle tara
python selenium_project.py --with-details --engine requests --workers 20

# Çıktıları başka bir klasöre yaz
python selenium_project.py --output-dir sonuclar
```

| Seçenek | Varsayılan | Açıklama |
|---|---|---|
| `--max-pages N` | tümü | Taranacak en fazla sayfa sayısı |
| `--workers N` | 10 | Paralel HTTP işçisi sayısı |
| `--with-details` | kapalı | Detay sayfalarını da tara (kategori, stok adedi) |
| `--engine` | `hybrid` | `hybrid` veya `requests`; yalnızca `--with-details` ile anlamlı |
| `--output-dir` | `output` | Çıktı klasörü |
| `--no-browser-open` | kapalı | Raporu otomatik açma |

Not: `hybrid` motor detay sayfalarını tek bir Chrome oturumuyla sırayla gezer, bu yüzden `requests` motorundan daha yavaştır.

## Çıktılar

Çıktı klasöründe (varsayılan `output/`) şu dosyalar oluşur:

- `books_data.db`: SQLite veritabanı
- `books_data.csv` ve `books_data.json`: tüm kitaplar
- `books_report.html`: görsel rapor

Repo kökündeki `books_report.html` örnek bir rapordur; indirip tarayıcıda açabilirsiniz.

## Veritabanı şeması

| Tablo | Alanlar |
|---|---|
| `books` | title, price, stock_status, stock_count, rating, category, page_number, url (benzersiz), updated_at |
| `price_history` | book_url, price, checked_at |
| `stock_history` | book_url, stock_count, checked_at |
| `scan_runs` | started_at, total_books, duration_seconds |

## Sınırlamalar

- CSS seçicileri Books to Scrape sitesinin yapısına göre yazılmıştır; başka sitelerde uyarlama gerekir.
- Eğitim amaçlı bir projedir, otomatik test içermez.
