from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import undetected as uc

def get_page_with_selenium(url: str, headers: dict) -> str:
    """
    Use Selenium to get the HTML content of a page after possible AWS WAF challenges.
    :param url: URL to load
    :param wait_selector: CSS selector to wait for (optional)
    :param headless: if True, browser window is not shown
    :param headers: dict of headers to set (User-Agent, Referer, ...)
    :return: HTML content of the page
    """
    chrome_options = Options()
    chrome_options.add_argument('--headless')  # Run in headless mode
    chrome_options.add_argument('--disable-gpu')
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--window-size=1920,1080')  # Set window size
    chrome_options.add_argument(f'--user-agent={headers["User-Agent"]}')  # Avoid headless detection
    driver = uc.Chrome(options=chrome_options)
    try:
        if headers and 'Referer' in headers:
            driver.execute_cdp_cmd('Network.setExtraHTTPHeaders', {'headers': {'Referer': headers['Referer']}})
        driver.get(url)
        # Wait for the real page title to appear (not the challenge page)
        WebDriverWait(driver, 30).until(EC.title_is('Portale Antenati'))
        # Optionally, you can still check status code as before (but not strictly needed)
        return driver.page_source
    except Exception as e:
        raise e
    finally:
        driver.quit()
