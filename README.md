# 📚 BookScope — Hybrid Web Scraper

> *Books to Scrape* kataloğunu yüksek hız (requests + ThreadPoolExecutor) ve hassas browser etkileşimi (Selenium) harmanlayarak tarayan, SQLite veritabanında geçmiş takibi yapan ve zenginleştirilmiş HTML raporlar üreten endüstriyel seviyede bir kazıma aracıdır.

---

## 🏛️ Mimari & Özellikler

* **Hibrit Motor (`hybrid`)**: Liste sayfaları `requests` + `ThreadPoolExecutor` ile paralel taranır; detay sayfaları ve dinamik bileşenler gerektiğinde `Selenium` ile işlenir.
* **Veritabanı Yönetimi (`SQLite`)**: 
  * `UPERT / ON CONFLICT` ile mevcut kayıtlar güncellenir.
  * `price_history` ve `stock_history` tabloları ile zaman bazlı fiyat/stok değişimleri izlenir.
  * Otomatik şema migrasyonu (`PRAGMA table_info`).
* **Görsel Raporlama**: `matplotlib` tabanlı baz64 gömülü grafikler (fiyat dağılımı, yıldız puanı dağılımı, stok durumu) ve kategori çubukları içeren tipografi odaklı şık HTML rapor.
* **Hata Yönetimi**: Selenium tabanlı detay taramalarında oluşan hatalar için otomatik ekran görüntüsü (`screenshots/error_X.png`) kaydı.

---

## ⚙️ Kurulum

1. **Repoyu klonlayın ve sanal ortamı oluşturun:**
   ```powershell
   git clone [https://github.com/canpolatinan/selenium-web-scraping.git](https://github.com/canpolatinan/selenium-web-scraping.git)
   cd selenium-web-scraping
   python -m venv .venv
   .venv\Scripts\activate
