import os
import json
import pandas as pd
import re
from datetime import datetime
import cohere
import requests
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
import streamlit as st
from io import BytesIO
import time

# Initialize API keys from environment variables
cohere_api_key = os.getenv("COHERE_API_KEY")
serpapi_key = os.getenv("SERPAPI_KEY")

def parse_event_date(date_str):
    date_str = date_str.strip()
    if not date_str:
        return "", ""

    # Normalize common range delimiters
    date_str = re.sub(r"\s?(to|–|\-|until)\s?", " to ", date_str)
    
    try:
        # Match date ranges like '12 May 2024 to 15 May 2024'
        range_match = re.search(r"(\d{1,2} \w+ \d{4}) to (\d{1,2} \w+ \d{4})", date_str)
        if range_match:
            start = datetime.strptime(range_match.group(1), "%d %B %Y").strftime("%Y-%m-%d")
            end = datetime.strptime(range_match.group(2), "%d %B %Y").strftime("%Y-%m-%d")
            return start, end
        else:
            # Fallback single date
            date = datetime.strptime(date_str, "%d %B %Y").strftime("%Y-%m-%d")
            return date, date
    except:
        return date_str, date_str

class EventJobScraper:
    def __init__(self):
        self.co = None
        self.validate_api_keys()
        self.initialize_cohere_client()

    def validate_api_keys(self):
        if not cohere_api_key or not serpapi_key:
            st.error("""
                Missing API keys. Please set:
                - COHERE_API_KEY
                - SERPAPI_KEY
            """)
            st.stop()

    def initialize_cohere_client(self):
        try:
            self.co = cohere.Client(cohere_api_key)
        except Exception as e:
            st.error(f"Cohere initialization failed: {str(e)}")
            st.stop()

    def generate_event_queries(self, user_input):
        try:
            response = self.co.generate(
                model='command-r-plus',
                prompt=f"""Generate 5 precise Google search queries to find upcoming job events for:
                \"{user_input}\". Focus on:
                - Job fairs
                - Career expos
                - Hiring events
                - Recruitment drives
                Return ONLY a JSON array: [\"query1\", \"query2\"]""",
                max_tokens=200,
                temperature=0.3
            )
            raw_text = response.generations[0].text.strip()
            if not raw_text.startswith("["):
                raw_text = "[" + raw_text
            if not raw_text.endswith("]"):
                raw_text += "]"
            return json.loads(raw_text)
        except:
            return [
                f'"{user_input}" job fair 2023',
                f'"{user_input}" career expo upcoming',
                f'"{user_input}" hiring event',
                f'"{user_input}" recruitment drive',
                f'"{user_input}" job opportunities event'
            ]

    def get_event_urls(self, query, num_results=10):
        params = {
            'q': query,
            'engine': 'google',
            'api_key': serpapi_key,
            'num': num_results,
            'tbs': 'qdr:m'
        }
        try:
            response = requests.get('https://serpapi.com/search', params=params)
            results = response.json()
            return [r['link'] for r in results.get('organic_results', []) if 'link' in r]
        except:
            return []

    def setup_driver(self):
        options = Options()
        options.add_argument("--headless=new")
        options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64)")
        service = Service(ChromeDriverManager().install())
        return webdriver.Chrome(service=service, options=options)

    def extract_event_details(self, url, driver):
        try:
            driver.get(url)
            time.sleep(2)
            page_text = driver.find_element(By.TAG_NAME, 'body').text[:3000]

            prompt = f"""Extract job event details in JSON format from the following text:

            {page_text}

            Return a JSON object with these fields:
            - event_name (string)
            - event_date (string)
            - event_location (string)
            - organizer (string)
            - registration_url (string)
            - description (string)
            - contact_email (string)
            - is_virtual (boolean)
            """

            response = self.co.generate(
                model="command-r-plus",
                prompt=prompt,
                max_tokens=400,
                temperature=0.2
            )
            data = json.loads(response.generations[0].text.strip())
            data['source_url'] = url
            start, end = parse_event_date(data.get('event_date', ''))
            data['start_date'] = start
            data['end_date'] = end
            return data
        except Exception as e:
            st.warning(f"Failed extracting from {url}: {str(e)}")
            return None

    def save_event_data(self, events, format='excel'):
        if not events:
            return None
        df = pd.DataFrame(events)
        if format == 'excel':
            output = BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                df.to_excel(writer, index=False)
            output.seek(0)
            return output
        return df.to_json(orient='records', indent=2)

def main():
    st.set_page_config(page_title="Job Event Scraper", layout="wide")
    st.title("🎯 Job Event Finder")

    scraper = EventJobScraper()

    st.subheader("Enter your job event search criteria")
    user_input = st.text_area(
        "Describe the type of job events you're looking for:",
        "e.g. 'Tech job fairs in New York for software engineers'",
        height=100
    )

    if st.button("🔍 Find Job Events", type="primary"):
        if not user_input.strip():
            st.warning("Please enter your search criteria")
            return

        with st.status("Processing your request...", expanded=True) as status:
            status.update(label="Generating search queries...")
            queries = scraper.generate_event_queries(user_input)

            status.update(label="Fetching event URLs...")
            urls = []
            for q in queries:
                urls.extend(scraper.get_event_urls(q))
            unique_urls = list(set(urls))[:15]

            if not unique_urls:
                st.error("No URLs found. Try again with different criteria.")
                return

            status.update(label="Extracting event details...")
            driver = scraper.setup_driver()
            events = []
            for url in unique_urls:
                result = scraper.extract_event_details(url, driver)
                if result:
                    events.append(result)
            driver.quit()
            status.update(label="Extraction complete", state="complete")

        if not events:
            st.warning("No structured event data extracted.")
            return

        st.success(f"Found {len(events)} job events!")

        tab1, tab2 = st.tabs(["Summary Table", "Detailed View"])
        with tab1:
            st.dataframe(pd.DataFrame(events)[['event_name', 'start_date', 'end_date', 'event_location', 'organizer']], use_container_width=True)
        with tab2:
            for e in events:
                with st.expander(e.get("event_name", "Unnamed Event")):
                    st.markdown(f"**Date:** {e.get('start_date', 'N/A')} to {e.get('end_date', 'N/A')}")
                    st.markdown(f"**Location:** {e.get('event_location', 'N/A')}")
                    st.markdown(f"**Organizer:** {e.get('organizer', 'N/A')}")
                    st.markdown(f"**Virtual:** {'Yes' if e.get('is_virtual') else 'No'}")
                    st.markdown(f"**Description:** {e.get('description', '')}")
                    if e.get('registration_url'):
                        st.markdown(f"[Register Here]({e['registration_url']})")
                    st.markdown(f"[Source]({e['source_url']})")

        excel_file = scraper.save_event_data(events, 'excel')
        json_file = scraper.save_event_data(events, 'json')

        st.download_button("📥 Download as Excel", data=excel_file, file_name="job_events.xlsx")
        st.download_button("📥 Download as JSON", data=json_file, file_name="job_events.json")

if __name__ == "__main__":
    main()
