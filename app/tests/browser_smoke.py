"""Manual real-browser smoke test for the integrated Smart BSF page.

Requires local Selenium/Chrome; not part of portable runtime dependencies.
Run: python app/tests/browser_smoke.py
"""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.request import urlopen

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

ROOT = Path(__file__).resolve().parents[2]


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def main() -> None:
    port = free_port()
    with tempfile.TemporaryDirectory(prefix="browser_smoke_") as temporary:
        env = {**os.environ, "FISCYCLE_BSF_API_PREFIX": "/custom/bsf",
               "FISCYCLE_BSF_HISTORY_DB": str(Path(temporary) / "history.sqlite3")}
        server = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1",
                                   "--port", str(port)], cwd=ROOT, env=env, stdout=subprocess.DEVNULL,
                                  stderr=subprocess.PIPE, text=True)
        driver = None
        try:
            for _ in range(60):
                if server.poll() is not None:
                    raise RuntimeError("Uvicorn exited before browser test: " + server.stderr.read()[-1200:])
                try:
                    with urlopen(f"http://127.0.0.1:{port}/custom/bsf/health", timeout=2) as response:
                        if response.status == 200:
                            break
                except Exception:
                    time.sleep(1)
            else:
                raise TimeoutError("Uvicorn did not become ready")
            options = webdriver.ChromeOptions()
            options.add_argument("--headless=new")
            options.add_argument("--disable-gpu")
            options.add_argument("--no-sandbox")
            cached = list((Path.home() / ".cache/selenium/chromedriver/win64").glob("*/chromedriver.exe"))
            cached.sort(key=lambda p: tuple(int(part) for part in p.parent.name.split(".")), reverse=True)
            driver = webdriver.Chrome(service=Service(str(cached[0])) if cached else Service(), options=options)
            driver.get(f"http://127.0.0.1:{port}/")
            WebDriverWait(driver, 30).until(EC.text_to_be_present_in_element((By.ID, "progress"), "1 /"))
            WebDriverWait(driver, 30).until(lambda browser: '"latest_result"' in browser.find_element(By.ID, "raw").get_attribute("textContent"))
            driver.find_element(By.ID, "next").click()
            WebDriverWait(driver, 30).until(EC.text_to_be_present_in_element((By.ID, "progress"), "2 /"))
            assert driver.find_element(By.LINK_TEXT, "Smart BSF").get_attribute("href").endswith("/bsf-intelligence")
            driver.get(f"http://127.0.0.1:{port}/bsf-intelligence")
            WebDriverWait(driver, 30).until(EC.text_to_be_present_in_element((By.ID, "overview-content"), "TERUKUR PENELITIAN"))
            assert "content=\"/custom/bsf\"" in driver.page_source
            assert driver.find_element(By.ID, "overview-content").find_elements(By.CSS_SELECTOR, "article")
            assert "Ringkasan BSF" in driver.page_source and "Analisis Foto" in driver.page_source
            driver.find_element(By.CSS_SELECTOR, '[data-screen="dss"]').click()
            Select(driver.find_element(By.ID, "dss-mode")).select_by_value("USER_ENTERED")
            batch = driver.find_element(By.ID, "manual-batch")
            batch.send_keys("batch-a")
            driver.find_element(By.ID, "manual-day").send_keys("1")
            driver.find_element(By.ID, "manual-weight").send_keys("50")
            driver.find_element(By.ID, "manual-add").click()
            WebDriverWait(driver, 20).until(EC.text_to_be_present_in_element((By.ID, "manual-list"), "50"))
            batch.clear()
            batch.send_keys("batch-b")
            WebDriverWait(driver, 5).until(EC.text_to_be_present_in_element((By.ID, "manual-list"), "ID batch berubah"))
            assert "50" not in driver.find_element(By.ID, "manual-list").text
            driver.get(f"http://127.0.0.1:{port}/ecosystem")
            WebDriverWait(driver, 30).until(lambda d: len(d.find_elements(By.CSS_SELECTOR,"#growth-select option"))==16)
            driver.find_element(By.ID,"photo-demo").click()
            WebDriverWait(driver, 90).until(EC.text_to_be_present_in_element((By.ID,"photo-result"),"Massa terlihat"))
            assert "dianalisis" in driver.find_element(By.ID,"photo-result").text
            WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.ID,"growth-demo"))).click()
            WebDriverWait(driver, 60).until(EC.text_to_be_present_in_element((By.ID,"growth-result"),"pasangan waktu cocok"))
            WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.ID,"water-demo"))).click()
            WebDriverWait(driver, 120).until(EC.text_to_be_present_in_element((By.ID,"water-result"),"Evaluasi pada pasangan yang sama"))
            assert "80 observasi" in driver.find_element(By.ID,"water-result").text
            WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.ID,"water-scenario"))).click()
            WebDriverWait(driver, 30).until(EC.text_to_be_present_in_element((By.ID,"scenario-result"),"Skenario: STALE"))
            WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.ID,"history-load"))).click()
            WebDriverWait(driver, 30).until(EC.text_to_be_present_in_element((By.ID,"history-result"),"WATER_SCENARIO"))
            driver.get(f"http://127.0.0.1:{port}/bsf-intelligence#gallery")
            WebDriverWait(driver, 40).until(lambda d: len(d.find_elements(By.CSS_SELECTOR,"#gallery-grid .gallery-card"))==20)
            assert "46 foto tercatat" in driver.find_element(By.ID,"gallery-inventory").text
            driver.find_element(By.ID,"gallery-next-page").click()
            WebDriverWait(driver, 20).until(EC.text_to_be_present_in_element((By.ID,"gallery-page"),"Halaman 2"))
            Select(driver.find_element(By.ID,"gallery-dataset")).select_by_value("a2-test")
            WebDriverWait(driver, 30).until(EC.text_to_be_present_in_element((By.ID,"gallery-inventory"),"178 foto tercatat"))
            search=driver.find_element(By.ID,"gallery-search");search.send_keys("A2_1081")
            WebDriverWait(driver, 30).until(lambda d: len(d.find_elements(By.CSS_SELECTOR,"#gallery-grid .gallery-card"))==1)
            driver.find_element(By.CSS_SELECTOR,"[data-gallery-open]").click()
            WebDriverWait(driver, 30).until(lambda d:d.find_element(By.ID,"gallery-original").get_property("naturalWidth")==4056)
            WebDriverWait(driver, 30).until(EC.text_to_be_present_in_element((By.ID,"gallery-detail-result"),"278"))
            driver.find_element(By.ID,"gallery-analyze").click()
            WebDriverWait(driver, 30).until(EC.text_to_be_present_in_element((By.ID,"gallery-message"),"Cache cocok"))
            driver.find_element(By.ID,"gallery-back").click()
            search=driver.find_element(By.ID,"gallery-search");search.clear();search.send_keys(" ");search.clear()
            Select(driver.find_element(By.ID,"gallery-status")).select_by_value("REJECTED")
            WebDriverWait(driver, 30).until(EC.text_to_be_present_in_element((By.ID,"gallery-page"),"48 foto sesuai filter"))
            Select(driver.find_element(By.ID,"gallery-status")).select_by_value("")
            Select(driver.find_element(By.ID,"gallery-dataset")).select_by_value("a1-test")
            WebDriverWait(driver, 30).until(EC.text_to_be_present_in_element((By.ID,"gallery-inventory"),"46 foto tercatat"))
            driver.find_element(By.ID,"gallery-bulk").click()
            WebDriverWait(driver, 60).until(EC.text_to_be_present_in_element((By.ID,"gallery-job-summary"),"46/46 selesai"))
            driver.find_element(By.CSS_SELECTOR,"[data-gallery-open]").click()
            WebDriverWait(driver, 30).until(EC.text_to_be_present_in_element((By.ID,"gallery-detail-result"),"Estimasi total berat larva"))
            for gallery_width in (390,768,1440):
                driver.set_window_size(gallery_width,900)
                assert driver.execute_script("return document.documentElement.scrollWidth <= window.innerWidth+2"), f"gallery detail overflow at {gallery_width}"
            driver.find_element(By.ID,"gallery-next-image").click()
            WebDriverWait(driver, 30).until(lambda d:d.find_element(By.ID,"gallery-original").get_property("naturalWidth")==640)
            driver.find_element(By.ID,"gallery-back").click()
            for screen_width in (390,768,1440):
                driver.set_window_size(screen_width,900)
                assert driver.execute_script("return document.documentElement.scrollWidth <= window.innerWidth+2"), f"overflow at {screen_width}"
            driver.set_window_size(390, 844)
            time.sleep(.5)
            width = driver.execute_script("return document.documentElement.scrollWidth")
            viewport = driver.execute_script("return window.innerWidth")
            assert width <= viewport + 2, f"mobile overflow: {width} > {viewport}"
            print("PASS: Chrome four real-model flows + complete A1/A2 gallery, pagination/search, 4056px original, cache, 48 rejected A2 remain visible, 46-item bulk, next image, existing modules, custom prefix, 390/768/1440px layouts")
        finally:
            if driver:
                driver.quit()
            server.terminate()
            try:
                server.wait(timeout=5)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait(timeout=5)


if __name__ == "__main__":
    main()
