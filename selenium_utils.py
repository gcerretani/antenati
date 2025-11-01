from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options

def get_page_with_selenium(url: str, wait_selector: str = None, headless: bool = True, headers: dict = None) -> str:
    """
    Use Selenium to get the HTML content of a page after possible AWS WAF challenges.
    :param url: URL to load
    :param wait_selector: CSS selector to wait for (optional)
    :param headless: if True, browser window is not shown
    :param headers: dict of headers to set (User-Agent, Referer, ...)
    :return: HTML content of the page
    """
    chrome_options = Options()
    if headless:
        chrome_options.add_argument('--headless')  # Run in headless mode
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--window-size=1920,1080')  # Set window size
    if headers:
        if 'User-Agent' in headers:
            chrome_options.add_argument(f"--user-agent={headers['User-Agent']}")
        # Referer and others can be set via CDP after driver creation
    driver = webdriver.Chrome(options=chrome_options)
    try:
        if headers and 'Referer' in headers:
            driver.execute_cdp_cmd('Network.setExtraHTTPHeaders', {"headers": {"Referer": headers['Referer']}})
        driver.get(url)
        if wait_selector:
            # Wait for the element specified by the CSS selector to be present
            from selenium.webdriver.support.ui import WebDriverWait
            from selenium.webdriver.support import expected_conditions as EC
            WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.CSS_SELECTOR, wait_selector)))
        return driver.page_source
    finally:
        driver.quit()
