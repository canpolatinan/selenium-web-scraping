# 📚 Advanced Books to Scraper & HTML Report Generator

Bu proje, Python ve Selenium kullanılarak geliştirilmiş, endüstriyel standartlara uygun, nesne yönelimli (OOP) ve görselleştirilmiş bir web scraping (veri kazıma) otomasyonudur. `books.toscrape.com` üzerindeki verileri yüksek performansla toplar, SQLite veritabanına kaydeder ve tarama bitince otomatik olarak grafikli bir HTML rapor paneli üretir.

---

## 🚀 Öne Çıkan Özellikler

* **Endüstriyel OOP Mimarisi:** Modüler ve sürdürülebilir sınıf yapısı (`BooksScraper`, `DatabaseManager`).
* **Yüksek Performans (Eager Loading):** Sayfaların gereksiz öğelerini beklemeden hızlı veri çekme stratejisi.
* **Veritabanı Entegrasyonu:** Toplanan tüm verilerin eşzamanlı olarak SQLite (`books_data.db`) veritabanına işlenmesi.
* **Görsel HTML Raporlama (Matplotlib):** `Agg` motoruyla ekran gerektirmeden fiyat ve yıldız dağılımı grafikleri üretme ve Base64 ile tek bir HTML dosyasına gömme (`books_report.html`).
* **Akıllı Hata Yönetimi & Retry:** Bağlantı kopmaları ve element gecikmelerine karşı otomatik yeniden deneme mekanizması.
* **Otomatik UX Deneyimi:** Tarama bittiği an oluşturulan şık dark-mode raporunun varsayılan tarayıcıda otomatik olarak açılması.

---

## 🛠️ Kullanılan Teknolojiler

* **Python 3.10+**
* **Selenium** (Web Otomasyonu)
* **SQLite3** (Veritabanı Yönetimi)
* **Matplotlib** (Veri Görselleştirme / Grafik)

---

## ⚙️ Kurulum ve Çalıştırma

1. Projeyi klonlayın:
   ```bash
   git clone [https://github.com/canpolatinan/selenium-web-scraping.git](https://github.com/canpolatinan/selenium-web-scraping.git)
   cd selenium-web-scraping
