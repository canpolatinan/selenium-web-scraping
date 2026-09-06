from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time

options = webdriver.ChromeOptions()
driver = webdriver.Chrome(options=options)

try:
    driver.get("https://books.toscrape.com/")

    print("Siteye başarıyla bağlandı, arama yapılıyor...")

    wait = WebDriverWait(driver, 10)

    first_book = wait.until(
        EC.element_to_be_clickable((By.CSS_SELECTOR, ".product_pod h3 a"))
    )
    book_title = first_book.get_attribute("title")
    print(f"Bulunan ilk ürün: {book_title}")

    first_book.click()

    price = wait.until(
        EC.presence_of_element_located((By.CSS_SELECTOR, ".price_color"))
    ).text

    print(f"Ürünün Fiyatı: {price}")

    time.sleep(3)

finally:
    driver.quit()
    print("Otomasyon başarıyla tamamlandı ve tarayıcı kapatıldı.")