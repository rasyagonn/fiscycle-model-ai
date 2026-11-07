"""Optional real-Chrome UI verification; requires Selenium and two running services."""
import json
import os
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC

ROOT = Path(__file__).resolve().parents[1]
BASE = os.getenv('FISCYCLE_AI_TEST_URL', 'http://127.0.0.1:3000')
OUTPUT = ROOT/'ai-service/.cache/browser'
OUTPUT.mkdir(parents=True, exist_ok=True)
options = webdriver.ChromeOptions()
options.add_argument('--headless=new')
options.add_argument('--disable-gpu')
options.add_argument('--no-first-run')
options.add_argument('--window-size=1440,1000')
options.set_capability('goog:loggingPrefs', {'browser': 'ALL'})
driver = webdriver.Chrome(options=options)
wait = WebDriverWait(driver, 120)
checks = []


def check(label, condition):
    assert condition, label
    checks.append({'check': label, 'status': 'PASS'})
    print('PASS', label, flush=True)


def click(label):
    element = WebDriverWait(driver, 25).until(EC.element_to_be_clickable((By.XPATH, "//button[normalize-space()="+json.dumps(label, ensure_ascii=False)+"]")))
    driver.execute_script("arguments[0].scrollIntoView({block:'center'})", element)
    element.click()


def tab(label):
    element = WebDriverWait(driver, 25).until(EC.element_to_be_clickable((By.XPATH, "//nav[@aria-label='Fitur AI']//button[contains(.,"+json.dumps(label, ensure_ascii=False)+")]")))
    driver.execute_script("arguments[0].scrollIntoView({block:'center'})", element)
    element.click()


def visible(test_id):
    return wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, '[data-testid="'+test_id+'"]')))


try:
    driver.get(BASE+'/desktop/ai')
    wait.until(lambda d: 'AI Service tersambung' in d.find_element(By.CSS_SELECTOR,'[data-testid="ai-status"]').text)
    check('Desktop shell and real model readiness', 'Pusat AI Fiscycle' in driver.find_element(By.TAG_NAME,'h1').text)
    check('Tailwind utilities compiled in production', driver.execute_script("return getComputedStyle(document.querySelector('nav[aria-label=\"Fitur AI\"]')).display") == 'flex')
    wait.until(lambda d: len(d.find_elements(By.CSS_SELECTOR,'select[aria-label="Periode Water"] option')) > 1)
    click('Mulai / ulang replay Water')
    visible('water-result')
    click('Lanjutkan 25 observasi')
    wait.until(lambda d: '25/' in visible('water-result').text)
    check('Water replay real observations, forecasts and DSS visible', 'Kualitas data:' in visible('water-result').text)
    driver.save_screenshot(str(OUTPUT/'desktop-water.png'))

    tab('Analisis foto')
    click('A2 · Satu larva')
    photo = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR,'button[aria-label="Analisis foto A2 nomor 1"]')))
    driver.execute_script("arguments[0].scrollIntoView({block:'center'})", photo)
    photo.click()
    result = visible('photo-result')
    check('A2 curated photo real inference and result', 'SUCCESS' in result.text or 'REJECTED' in result.text)

    upload = driver.find_element(By.CSS_SELECTOR,'input[aria-label="Foto BSF"]')
    upload.send_keys(str(ROOT/'ai-service/tests/fixtures/a1_development_train.jpg'))
    Select(driver.find_element(By.CSS_SELECTOR,'select[aria-label="Jenis analisis foto"]')).select_by_value('segment')
    click('Jalankan analisis foto')
    expected = json.loads((ROOT/'ai-service/tests/fixtures/golden_reference.json').read_text())['a1_visible_instance_count']
    wait.until(lambda d: visible('photo-result').find_element(By.XPATH,".//p[normalize-space()='Larva terlihat terdeteksi']/following-sibling::p").text == str(expected))
    check('Real file upload reaches A1 and displays detector count', visible('photo-result').find_element(By.XPATH,".//p[normalize-space()='Larva terlihat terdeteksi']/following-sibling::p").text == str(expected))

    upload.send_keys(str(ROOT/'ai-service/tests/fixtures/a2_development_train.jpg'))
    Select(driver.find_element(By.CSS_SELECTOR,'select[aria-label="Jenis analisis foto"]')).select_by_value('estimate-weight')
    roi = json.loads((ROOT/'ai-service/tests/fixtures/fixture_metadata.json').read_text())['a2']['roi_bbox']
    for key, value in zip(['x0','y0','x1','y1'], roi):
        driver.find_element(By.CSS_SELECTOR,'input[aria-label="ROI '+key+'"]').send_keys(str(value))
    checkbox = driver.find_element(By.CSS_SELECTOR,'input[type="checkbox"]')
    driver.execute_script("arguments[0].scrollIntoView({block:'center'})", checkbox)
    checkbox.click()
    click('Jalankan analisis foto')
    wait.until(lambda d: visible('photo-result').find_element(By.XPATH,".//p[normalize-space()='Estimasi berat per larva (mg)']/following-sibling::p").text != '—')
    # The numeric golden is asserted by the HTTP test; verify the reviewed-ROI form flow here.
    check('A2 reviewed-ROI upload renders model preview', visible('photo-result').is_displayed())

    tab('Pertumbuhan BSF')
    click('Buka replay B1')
    wait.until(lambda d: '2/' in visible('b1-result').text)
    click('Observasi berikutnya')
    wait.until(lambda d: '3/' in visible('b1-result').text)
    check('B1 historical stepping and predicted weight rendered', 'mg/individu' in visible('b1-result').text)
    driver.save_screenshot(str(OUTPUT/'desktop-bsf.png'))

    tab('Penjelasan DSS')
    click('Jelaskan penilaian DSS')
    result = visible('dss-result')
    check('DSS explanations and factor registry rendered', 'Faktor dan asal data' in result.text)

    tab('Riwayat')
    click('Muat riwayat')
    wait.until(EC.visibility_of_element_located((By.XPATH,"//summary[contains(.,'Penjelasan DSS #')]")))
    check('Actual analysis history visible', 'Penjelasan DSS #' in driver.find_element(By.TAG_NAME,'body').text)

    for width in [390,768]:
        driver.set_window_size(width,900)
        driver.get(BASE+'/mitra/ai')
        wait.until(lambda d: 'AI Service tersambung' in visible('ai-status').text)
        dimensions = driver.execute_script('return {width:innerWidth, scroll:document.documentElement.scrollWidth}')
        check('Mitra AI responsive without horizontal overflow at '+str(width), dimensions['scroll'] <= dimensions['width']+1)
        driver.save_screenshot(str(OUTPUT/('mitra-'+str(width)+'.png')))

    driver.set_window_size(1440,1000)
    driver.get(BASE+'/mitra/dashboard')
    wait.until(lambda d: 'Ringkasan operasional' in d.find_element(By.TAG_NAME,'body').text)
    check('Existing pond dashboard retained with truthful demo label', bool(driver.find_elements(By.CSS_SELECTOR,'a[href="/mitra/ai"]')))
    # Existing six-step circular workflow is executed through the existing UI.
    click('⚡ Pitch Mode')
    click('✅ Self-Test 6 Assertions')
    wait.until(lambda d: 'Golden Thread LULUS 100%' in d.find_element(By.TAG_NAME,'body').text or 'Self-Test Gagal' in d.find_element(By.TAG_NAME,'body').text)
    body = driver.find_element(By.TAG_NAME,'body').text
    check('Existing six-step Golden Thread self-test passes', 'Self-Test Gagal' not in body and 'Golden Thread LULUS 100%' in body)
    errors = [e['message'] for e in driver.get_log('browser') if e['level']=='SEVERE']
    # Application exceptions fail; resource messages are reported independently.
    runtime_errors = [m for m in errors if any(k in m for k in ['Uncaught','TypeError:','Hydration failed'])]
    check('No uncaught browser or hydration errors', not runtime_errors)
    check('No missing browser resources', not errors)
    report = {'status':'PASS','scope':'REAL_HEADLESS_CHROME_UI','checks':checks,'resource_errors':errors}
    (OUTPUT/'RESULTS.json').write_text(json.dumps(report,indent=2)+'\n')
except Exception:
    driver.save_screenshot(str(OUTPUT/'FAILURE.png'))
    raise
finally:
    driver.quit()
