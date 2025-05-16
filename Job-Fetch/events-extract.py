import requests
from bs4 import BeautifulSoup
import cohere
import json
import openpyxl
import time
from dateutil import parser
from datetime import datetime
import re
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

# === CONFIGURATION ===
COHERE_API_KEY = "0QN0RcpBkIfA1PNfGDOfMMRtU5kOcJLAq6jtRTVT"
INPUT_FILE = "event_urls_serpapi.json"
OUTPUT_JSON = "extracted_upcoming_events.json"
OUTPUT_EXCEL = "extracted_upcoming_events.xlsx"

# === INITIALIZE COHERE ===
co = cohere.Client(COHERE_API_KEY)

# === PROMPT TEMPLATE ===
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

# === LOAD URLS ===
def load_urls():
    with open(INPUT_FILE, "r") as f:
        return json.load(f)

# === FETCH PAGE CONTENT USING SELENIUM ===
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
        time.sleep(3)  # wait for JavaScript to render
        page_text = driver.find_element("tag name", "body").text
        driver.quit()
        return page_text
    except Exception as e:
        print(f"[ERROR] Selenium failed to fetch {url}: {e}")
        return None

# === EXTRACT EVENTS USING COHERE ===
def extract_events(text, url):
    try:
        prompt = build_prompt(text, url)
        print(f"[COHERE] Calling Cohere API for: {url}")
        response = co.chat(message=prompt)

        time.sleep(6)  # Cohere rate limit

        json_start = response.text.find("[")
        json_end = response.text.rfind("]") + 1
        if json_start != -1 and json_end != -1:
            event_data = json.loads(response.text[json_start:json_end])
            return event_data
        else:
            print(f"[WARN] No JSON detected in response for {url}")
            return []
    except Exception as e:
        print(f"[ERROR] Cohere extraction failed for {url}: {e}")
        return []

# === FILTER UPCOMING EVENTS ===
def filter_upcoming_events(events):
    upcoming = []
    today = datetime.now().date()

    for event in events:
        try:
            date_str = event.get("event_date", "")
            if not date_str:
                continue

            # Handle date ranges
            if "to" in date_str:
                match = re.search(r'(\d{1,2}[a-z]{2}\s\w+\s\d{4})', date_str)
                if match:
                    date_str = match.group(1)

            if date_str.lower() == "not specified":
                continue

            event_dt = parser.parse(date_str, fuzzy=True).date()

            if event_dt >= today:
                upcoming.append(event)
        except Exception as e:
            print(f"[SKIP] Could not parse date '{event.get('event_date')}' - {e}")

    return upcoming

# === SAVE TO JSON ===
def save_json(data, filename):
    with open(filename, "w") as f:
        json.dump(data, f, indent=2)
    print(f"[SAVED] JSON saved to {filename}")

# === SAVE TO EXCEL ===
def save_excel(data, filename):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Event Name", "Event Date", "Event Location", "Organization", "Source URL"])
    for event in data:
        ws.append([
            event.get("event_name", ""),
            event.get("event_date", ""),
            event.get("event_location", ""),
            event.get("organization", ""),
            event.get("source_url", "")
        ])
    wb.save(filename)
    print(f"[SAVED] Excel saved to {filename}")

# === MAIN ===
def main():
    all_events = []
    url_entries = load_urls()

    for entry in url_entries:
        url = entry["URL"]
        text = fetch_page_text(url)
        if text:
            events = extract_events(text, url)
            upcoming_events = filter_upcoming_events(events)
            all_events.extend(upcoming_events)
        time.sleep(1.5)

    save_json(all_events, OUTPUT_JSON)
    save_excel(all_events, OUTPUT_EXCEL)

if __name__ == "__main__":
    main()
