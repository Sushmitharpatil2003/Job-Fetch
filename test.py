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

# Initialize API keys from environment variables
cohere_api_key = os.getenv("COHERE_API_KEY")
serpapi_key = os.getenv("SERPAPI_KEY")

class JobScraper:
    def __init__(self):
        self.co = None
        self.validate_api_keys()
        self.initialize_cohere_client()
        
    def validate_api_keys(self):
        """Check if required API keys are available"""
        if not cohere_api_key or not serpapi_key:
            st.error("""
                API keys not found. Please set these environment variables:
                - COHERE_API_KEY: Your Cohere API key
                - SERPAPI_KEY: Your SerpAPI key
                
                On Windows:
                ```
                set COHERE_API_KEY=your_key_here
                set SERPAPI_KEY=your_key_here
                ```
                
                On macOS/Linux:
                ```
                export COHERE_API_KEY=your_key_here
                export SERPAPI_KEY=your_key_here
                ```
                Then restart your Streamlit application.
            """)
            st.stop()
    
    def initialize_cohere_client(self):
        """Initialize the Cohere client"""
        try:
            self.co = cohere.Client(cohere_api_key)
        except Exception as e:
            st.error(f"Failed to initialize Cohere client: {e}")
            st.stop()

    def analyze_prompt_with_cohere(self, prompt):
        """Use Cohere to analyze the prompt and generate search queries."""
        response = self.co.generate(
            model='command',
            prompt=f"""Analyze this job search prompt and generate the most effective search queries for job boards. 
            Return 5 search queries in JSON format like {{"queries": ["query1", "query2", "query","query4","query5"]}}.
            
            Prompt: {prompt}""",
            max_tokens=150,
            temperature=0.7
        )
        
        try:
            queries = json.loads(response.generations[0].text)
            return queries.get('queries', [prompt])  # Fallback to original prompt if parsing fails
        except:
            return [prompt]

    def get_search_results(self, query, num_results=10):
        """Get search results using SerpAPI (Google Search API)"""
        params = {
            'q': query,  # Removed site restriction
            'engine': 'google',
            'api_key': serpapi_key,
            'num': num_results
        }

        try:
            response = requests.get('https://serpapi.com/search', params=params)
            results = response.json()
            return [result.get('link') for result in results.get('organic_results', [])]
        except Exception as e:
            st.error(f"Error fetching search results: {e}")
            return []

    def setup_selenium_driver(self):
        """Set up Selenium WebDriver with headless options"""
        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--window-size=1920x1080")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
        return driver

    def extract_emails(self, text):
        """Extract email addresses from text using regex"""
        email_regex = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
        return re.findall(email_regex, text)

    def extract_phones(self, text):
        """Extract phone numbers from text using regex"""
        phone_regex = r'(\d{3}[-\.\s]??\d{3}[-\.\s]??\d{4}|\(\d{3}\)\s*\d{3}[-\.\s]??\d{4}|\d{3}[-\.\s]??\d{4})'
        return re.findall(phone_regex, text)

    def scrape_job_details(self, url, driver):
        """Scrape job details from a given URL including contact information"""
        try:
            driver.get(url)
            driver.implicitly_wait(3)
            
            # Get all text from page for contact info extraction
            page_text = driver.find_element(By.TAG_NAME, 'body').text
            
            # Extract contact info
            emails = self.extract_emails(page_text)
            phones = self.extract_phones(page_text)
            
            # Initialize job data with all possible fields
            job_data = {
                'title': '',
                'company': '',
                'location': '',
                'description': '',
                'posted_date': datetime.now().strftime('%Y-%m-%d'),
                'url': url,
                'source': url.split('/')[2],
                'emails': ', '.join(list(set(emails))),  # Remove duplicates
                'phone_numbers': ', '.join(list(set(phones))),  # Remove duplicates
                'contact_page': url + '/contact' if '/contact' not in url else url,
                'linkedin': ''  # Initialize with empty string
            }
            
            # Try to get standard job details
            try:
                job_data['title'] = driver.find_element(By.TAG_NAME, 'h1').text if driver.find_elements(By.TAG_NAME, 'h1') else ''
            except:
                pass
                
            try:
                job_data['company'] = driver.find_element(By.CSS_SELECTOR, '.company-name').text if driver.find_elements(By.CSS_SELECTOR, '.company-name') else ''
            except:
                pass
                
            try:
                job_data['location'] = driver.find_element(By.CSS_SELECTOR, '.job-location').text if driver.find_elements(By.CSS_SELECTOR, '.job-location') else ''
            except:
                pass
                
            try:
                job_data['description'] = driver.find_element(By.CSS_SELECTOR, '.job-description').text if driver.find_elements(By.CSS_SELECTOR, '.job-description') else ''
            except:
                pass
            
            # Try to find LinkedIn profile if on company website
            if 'linkedin.com' not in url.lower():
                try:
                    linkedin_link = driver.find_element(By.XPATH, "//a[contains(@href, 'linkedin.com')]")
                    job_data['linkedin'] = linkedin_link.get_attribute('href')
                except:
                    pass
            
            return job_data
        except Exception as e:
            st.warning(f"Could not extract details from {url}: {str(e)}")
            return None

    def save_to_excel(self, jobs_data, filename="job_listings.xlsx"):
        """Save job data to Excel file"""
        # Ensure all records have all columns
        columns = ['title', 'company', 'location', 'description', 'posted_date', 
                  'url', 'source', 'emails', 'phone_numbers', 'contact_page', 'linkedin']
        
        # Create DataFrame with consistent columns
        df = pd.DataFrame(jobs_data, columns=columns)
        
        # Reorder columns to put contact info at the end
        cols = [col for col in df.columns if col not in ['emails', 'phone_numbers', 'linkedin', 'contact_page']]
        cols.extend(['emails', 'phone_numbers', 'linkedin', 'contact_page'])
        df = df[cols]
        
        output = BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df.to_excel(writer, index=False, sheet_name='Job Listings')
        return output.getvalue()

    def save_to_json(self, jobs_data, filename="job_listings.json"):
        """Save job data to JSON file"""
        return json.dumps(jobs_data, indent=2)

def main():
    st.title("AI-Powered Job Scraper with Contact Details")
    
    # Initialize the scraper
    scraper = JobScraper()
    
    st.write("Enter your job search prompt and get job listings with contact information!")
    
    # User input
    user_prompt = st.text_area("Describe the job you're looking for:", 
                              "e.g. 'Remote Python developer jobs with Django experience'")
    
    if st.button("Search Jobs"):
        with st.spinner("Analyzing your request and searching for jobs..."):
            # Step 1: Analyze prompt with Cohere
            queries = scraper.analyze_prompt_with_cohere(user_prompt)
            st.success(f"Generated search queries: {', '.join(queries)}")
            
            # Step 2: Get search results
            all_urls = []
            for query in queries[:2]:  # Limit to 2 queries to avoid too many requests
                urls = scraper.get_search_results(query)
                all_urls.extend(urls)
            
            unique_urls = list(set(all_urls))[:20]  # Limit to 20 unique URLs
            
            if not unique_urls:
                st.error("No search results found. Please try a different search term.")
                return
            
            # Step 3: Scrape job details
            driver = scraper.setup_selenium_driver()
            jobs_data = []
            
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            for i, url in enumerate(unique_urls):
                progress_bar.progress((i + 1) / len(unique_urls))
                status_text.text(f"Processing {i+1}/{len(unique_urls)}: {url}")
                job_data = scraper.scrape_job_details(url, driver)
                if job_data:
                    jobs_data.append(job_data)
            
            driver.quit()
            status_text.empty()
            
            if not jobs_data:
                st.error("No job details could be extracted. Please try different search terms.")
                return
            
            # Display results
            st.subheader(f"Found {len(jobs_data)} Job Listings")
            
            # Create tabs for different views
            tab1, tab2 = st.tabs(["All Data", "Contact Info Only"])
            
            with tab1:
                st.dataframe(pd.DataFrame(jobs_data))
            
            with tab2:
                # Safely get contact info columns, filling missing values with empty strings
                contact_data = []
                for job in jobs_data:
                    contact_data.append({
                        'company': job.get('company', ''),
                        'title': job.get('title', ''),
                        'emails': job.get('emails', ''),
                        'phone_numbers': job.get('phone_numbers', ''),
                        'linkedin': job.get('linkedin', ''),
                        'contact_page': job.get('contact_page', '')
                    })
                contact_df = pd.DataFrame(contact_data)
                st.dataframe(contact_df)
            
            # Create download buttons
            st.subheader("Download Results")
            
            excel_data = scraper.save_to_excel(jobs_data)
            st.download_button(
                label="Download as Excel",
                data=excel_data,
                file_name="job_listings.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
            
            json_data = scraper.save_to_json(jobs_data)
            st.download_button(
                label="Download as JSON",
                data=json_data,
                file_name="job_listings.json",
                mime="application/json"
            )

if __name__ == "__main__":
    main()