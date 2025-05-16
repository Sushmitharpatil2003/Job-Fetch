import requests
from bs4 import BeautifulSoup
import json
import re
import pandas as pd
import time
import random
from datetime import datetime

# ====== SETUP ======

API_KEY = "AIzaSyBOQ6VgcXiZE57KDzQsRCaTXPKdoM3EsDA"
CSE_ID = "1362da237761d4d96"

current_year = datetime.now().year
current_month = datetime.now().strftime("%B")

# Refined event-focused queries
queries = [
    f"{current_month} {current_year} job fair event site:.in",
    f"{current_month} {current_year} IT recruitment drive site:.in",
    f"{current_month} {current_year} campus hiring event site:.in",
    f"{current_month} {current_year} walk-in interview schedule site:.in",
    f"{current_month} {current_year} virtual career expo site:.in",
    f"{current_month} {current_year} online job event site:.in"
]

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
    "Mozilla/5.0 (X11; Linux x86_64)"
]

# ====== UTILITY FUNCTIONS ======

def human_pause(min_sec=5, max_sec=10):
    pause = random.uniform(min_sec, max_sec)
    print(f"⏳ Pausing for {pause:.2f} seconds...")
    time.sleep(pause)

def get_headers():
    return {"User-Agent": random.choice(USER_AGENTS)}

def google_search(query, api_key, cse_id, num=20):
    """Paginate through search results"""
    all_links = []
    for start in range(1, num + 1, 10):
        try:
            params = {
                "q": query,
                "key": api_key,
                "cx": cse_id,
                "start": start
            }
            response = requests.get("https://www.googleapis.com/customsearch/v1", params=params)
            results = response.json().get("items", [])
            all_links.extend([item["link"] for item in results])
        except Exception as e:
            print(f"❌ Google Search error: {e}")
    return all_links

def extract_text_from_url(url):
    """Scrape plain text content from webpage"""
    try:
        headers = get_headers()
        response = requests.get(url, headers=headers, timeout=10)

        content_type = response.headers.get("Content-Type", "")
        if not content_type.startswith("text/html"):
            print(f"⚠️ Skipping non-HTML content ({content_type}) at {url}")
            return ""

        soup = BeautifulSoup(response.text, "html.parser")
        for tag in soup(["script", "style"]): tag.decompose()
        text = soup.get_text(separator=' ')
        return re.sub(r'\s+', ' ', text).strip()
    except Exception as e:
        print(f"❌ Failed to extract {url}: {e}")
        return ""

def is_likely_event_page(text):
    """Check if content likely describes a real event"""
    event_keywords = [
        "job fair", "walk-in", "hiring event", "recruitment drive",
        "career expo", "virtual job fair", "register", "registration",
        "venue", "interview date", "join us", "career opportunity", "apply now"
    ]
    found = [kw for kw in event_keywords if kw.lower() in text.lower()]
    return len(found) >= 2

# ====== MAIN FUNCTION ======

def main():
    all_data = []
    seen_urls = set()

    for query in queries:
        print(f"\n🔍 Searching: {query}")
        urls = google_search(query, API_KEY, CSE_ID, num=20)
        human_pause()

        for url in urls:
            if url in seen_urls:
                continue
            seen_urls.add(url)

            print(f"\n🌐 Processing: {url}")
            text = extract_text_from_url(url)
            if text and is_likely_event_page(text):
                print(f"✅ Event-related content found.")
                all_data.append({
                    "URL": url
                })
            else:
                print("⚠️ Not an event page or no relevant content.")
            human_pause()

    # Save data
    with open("event_urls.json", "w") as f:
        json.dump(all_data, f, indent=2)

    pd.DataFrame(all_data).to_excel("event_urls.xlsx", index=False)
    print("\n📁 Saved: event_urls.json and event_urls.xlsx")

# ====== ENTRY POINT ======

if __name__ == "__main__":
    main()
