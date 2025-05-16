import time
import json
import re
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from bs4 import BeautifulSoup
import cohere
from webdriver_manager.chrome import ChromeDriverManager

# === CONFIGURATION ===
COHERE_API_KEY = "0QN0RcpBkIfA1PNfGDOfMMRtU5kOcJLAq6jtRTVT"
TEST_URL = "https://mybharat.gov.in/pages/event_detail?event_name=JOB-FAIR&key=851110452851"
# === INITIALIZE COHERE ===
co = cohere.Client(COHERE_API_KEY)

# === BUILD PROMPT ===
def build_prompt(text, url):
    return f"""
You are a helpful assistant that extracts structured job/career-related event information from web page text.

From the following content from this page: {url}

{text}

Extract only real job-related events — such as company hiring drives, walk-in interviews, job recruitments, or job fairs (only if they involve actual job opportunities).
Ignore general articles, webinars, counseling sessions, non-hiring career fairs, and content not related to jobs.

Only include events that take place in India.

Return the results in this exact JSON format:

[ 
  {{
    "event_name": "...",
    "event_date": "...",
    "event_location": "...",
    "organization": "...",
    "source_url": "..."
  }} 
]

Only return the JSON. If there are no valid job events in India, return []. 
"""

# === FETCH PAGE TEXT ===
def fetch_page_text(url):
    try:
        print(f"[SELENIUM FETCH] {url}")
        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")

        driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
        driver.set_page_load_timeout(20)
        driver.get(url)
        time.sleep(3)  # Allow JS to load

        html = driver.page_source
        driver.quit()

        soup = BeautifulSoup(html, "html.parser")

        # Remove non-text elements
        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()

        # Get clean structured text
        structured_text = soup.get_text(separator="\n", strip=True)
        return structured_text

    except Exception as e:
        print(f"[ERROR] Selenium failed to fetch {url}: {e}")
        return None

# === TESTING FUNCTION ===
def test_url(url):
    print(f"\n=== Testing URL ===\n{url}\n")

    text = fetch_page_text(url)
    if not text or len(text) < 100:
        print("[WARN] Page content too short or missing.")
        return

    print(f"[INFO] Extracted text length: {len(text)} characters")

    prompt = build_prompt(text, url)
    print(f"\n--- Prompt Preview (first 500 chars) ---\n{prompt[:500]}...\n")

    try:
        response = co.chat(message=prompt)
        print("\n--- Raw Response Text ---\n")
        print(response.text)

        json_start = response.text.find("[")
        json_end = response.text.rfind("]") + 1
        if json_start != -1 and json_end != -1:
            events = json.loads(response.text[json_start:json_end])
            print("\n✅ Parsed Events:")
            print(json.dumps(events, indent=2))
        else:
            print("\n❌ No valid JSON found in response.")
    except Exception as e:
        print(f"\n[ERROR] Cohere API call failed: {e}")

# === RUN ===
if __name__ == "__main__":
    test_url(TEST_URL)
