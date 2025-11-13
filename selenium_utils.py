from selenium import webdriver
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

def get_page(url: str, headers: dict) -> str:
    """
    Use Selenium to get the HTML content of a page after possible AWS WAF challenges.
    """
    driver = webdriver.Chrome()
    try:
        if headers and 'Referer' in headers:
            driver.execute_cdp_cmd('Network.setExtraHTTPHeaders', {'headers': {'Referer': headers['Referer']}})
        driver.get(url)
        # Wait for the real page title to appear (not the challenge page)
        WebDriverWait(driver, 30).until(EC.title_is('Portale Antenati'))
        # Optionally, you can still check status code as before (but not strictly needed)
        return driver.page_source
    finally:
        driver.quit()
