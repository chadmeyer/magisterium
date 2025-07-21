#!/usr/bin/env python3
"""
Vatican Website Scraper for Pope Leo's Magisterial Acts

This script crawls the Vatican website to collect all of Pope Leo's writings,
speeches, and other magisterial documents, storing them in a JSON format
that supports read status, comments, and quotes.
"""

import requests
from bs4 import BeautifulSoup
import json
import time
import re
from urllib.parse import urljoin, urlparse
from datetime import datetime
import argparse
from pathlib import Path

class VaticanScraper:
    def __init__(self, data_file="pope_leo_documents.json", delay=1.0):
        self.data_file = Path(data_file)
        self.delay = delay  # Delay between requests to be respectful
        self.base_url = "https://www.vatican.va"
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (compatible; Academic Research Bot)'
        })
        
        # Load existing data
        self.documents = self.load_existing_data()
        
    def load_existing_data(self):
        """Load existing document data, preserving user modifications"""
        if self.data_file.exists():
            try:
                with open(self.data_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                print(f"Loaded {len(data.get('documents', []))} existing documents")
                return data
            except (json.JSONDecodeError, FileNotFoundError) as e:
                print(f"Error loading existing data: {e}")
                print("Starting with fresh data...")
        
        return {
            "metadata": {
                "last_updated": None,
                "pope": "Leo XIII",
                "source": "vatican.va",
                "total_documents": 0
            },
            "documents": []
        }
    
    def save_data(self):
        """Save document data to JSON file"""
        self.documents["metadata"]["last_updated"] = datetime.now().isoformat()
        self.documents["metadata"]["total_documents"] = len(self.documents["documents"])
        
        with open(self.data_file, 'w', encoding='utf-8') as f:
            json.dump(self.documents, f, indent=2, ensure_ascii=False)
        
        print(f"Saved {len(self.documents['documents'])} documents to {self.data_file}")
    
    def document_exists(self, title, url):
        """Check if document already exists in our data"""
        for doc in self.documents["documents"]:
            if doc["title"] == title or doc["url"] == url:
                return doc
        return None
    
    def add_or_update_document(self, title, url, doc_type="", date="", language="", description=""):
        """Add new document or update existing one while preserving user data"""
        existing = self.document_exists(title, url)
        
        if existing:
            # Update URL if it's new/different (e.g., English translation added)
            if url not in existing.get("urls", [existing["url"]]):
                if "urls" not in existing:
                    existing["urls"] = [existing["url"]]
                existing["urls"].append(url)
                existing["url"] = url  # Update primary URL
                print(f"Updated URLs for: {title}")
            
            # Update other metadata if provided
            if doc_type and not existing.get("type"):
                existing["type"] = doc_type
            if date and not existing.get("date"):
                existing["date"] = date
            if language and language not in existing.get("languages", []):
                if "languages" not in existing:
                    existing["languages"] = [language]
                else:
                    existing["languages"].append(language)
            if description and not existing.get("description"):
                existing["description"] = description
                
            return existing
        else:
            # Create new document
            new_doc = {
                "title": title,
                "url": url,
                "type": doc_type,
                "date": date,
                "language": language,
                "languages": [language] if language else [],
                "description": description,
                "read": False,
                "comments": "",
                "quotes": [],
                "added_date": datetime.now().isoformat()
            }
            
            self.documents["documents"].append(new_doc)
            print(f"Added new document: {title}")
            return new_doc
    
    def fetch_page(self, url):
        """Fetch a webpage with error handling and rate limiting"""
        try:
            time.sleep(self.delay)
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            return BeautifulSoup(response.content, 'html.parser')
        except requests.RequestException as e:
            print(f"Error fetching {url}: {e}")
            return None
    
    def find_pope_leo_pages(self):
        """Find all pages related to Pope Leo XIII on vatican.va"""
        # Known starting points for Pope Leo XIII documents
        search_urls = [
            # Encyclicals
            f"{self.base_url}/content/leo-xiii/en/encyclicals.index.html",
            f"{self.base_url}/content/leo-xiii/la/encyclicals.index.html",
            f"{self.base_url}/content/leo-xiii/it/encyclicals.index.html",
            
            # Letters
            f"{self.base_url}/content/leo-xiii/en/letters.index.html",
            f"{self.base_url}/content/leo-xiii/la/letters.index.html",
            
            # Speeches
            f"{self.base_url}/content/leo-xiii/en/speeches.index.html",
            f"{self.base_url}/content/leo-xiii/la/speeches.index.html",
            
            # Main page
            f"{self.base_url}/content/leo-xiii/en.html",
            f"{self.base_url}/content/leo-xiii/la.html",
            f"{self.base_url}/content/leo-xiii/it.html",
        ]
        
        all_document_links = set()
        
        for url in search_urls:
            print(f"Checking: {url}")
            soup = self.fetch_page(url)
            if not soup:
                continue
                
            # Look for document links
            links = soup.find_all('a', href=True)
            for link in links:
                href = link['href']
                
                # Convert relative URLs to absolute
                full_url = urljoin(url, href)
                
                # Filter for Leo XIII document pages
                if (('/leo-xiii/' in full_url or '/leo_xiii/' in full_url) and 
                    full_url.endswith('.html') and
                    '/index.html' not in full_url and
                    full_url != url):
                    all_document_links.add(full_url)
        
        return list(all_document_links)
    
    def extract_document_info(self, url):
        """Extract document information from a Vatican page"""
        soup = self.fetch_page(url)
        if not soup:
            return None
        
        # Try to extract title
        title = ""
        title_selectors = [
            'h1', 'h2.doc_title', '.doc_title', '.title', 
            'title', 'h2', '.content h1', '.content h2'
        ]
        
        for selector in title_selectors:
            element = soup.select_one(selector)
            if element and element.get_text().strip():
                title = element.get_text().strip()
                break
        
        if not title:
            title = urlparse(url).path.split('/')[-1].replace('.html', '').replace('-', ' ').title()
        
        # Clean up title
        title = re.sub(r'\s+', ' ', title).strip()
        
        # Extract document type from URL or content
        doc_type = "Unknown"
        if '/encyclicals/' in url:
            doc_type = "Encyclical"
        elif '/letters/' in url:
            doc_type = "Letter"
        elif '/speeches/' in url:
            doc_type = "Speech"
        elif '/apost_letters/' in url:
            doc_type = "Apostolic Letter"
        
        # Extract language from URL
        language = "Latin"  # Default for Leo XIII era
        if '/en/' in url:
            language = "English"
        elif '/it/' in url:
            language = "Italian"
        elif '/fr/' in url:
            language = "French"
        elif '/de/' in url:
            language = "German"
        elif '/es/' in url:
            language = "Spanish"
        
        # Try to extract date
        date = ""
        date_patterns = [
            r'(\d{1,2})\s+(\w+)\s+(\d{4})',  # 15 May 1891
            r'(\d{4})-(\d{2})-(\d{2})',      # 1891-05-15
            r'(\w+)\s+(\d{1,2}),\s+(\d{4})', # May 15, 1891
        ]
        
        text_content = soup.get_text()
        for pattern in date_patterns:
            match = re.search(pattern, text_content)
            if match:
                date = match.group(0)
                break
        
        # Try to get description from first paragraph
        description = ""
        first_p = soup.select_one('p')
        if first_p:
            desc_text = first_p.get_text().strip()
            if len(desc_text) > 50:
                description = desc_text[:200] + "..." if len(desc_text) > 200 else desc_text
        
        return {
            'title': title,
            'url': url,
            'type': doc_type,
            'date': date,
            'language': language,
            'description': description
        }
    
    def scrape_all_documents(self):
        """Main scraping function"""
        print("Starting Vatican website scrape for Pope Leo XIII documents...")
        
        # Find all document pages
        document_urls = self.find_pope_leo_pages()
        print(f"Found {len(document_urls)} potential document pages")
        
        processed = 0
        new_docs = 0
        updated_docs = 0
        
        for url in document_urls:
            print(f"Processing ({processed + 1}/{len(document_urls)}): {url}")
            
            doc_info = self.extract_document_info(url)
            if doc_info:
                existing = self.document_exists(doc_info['title'], doc_info['url'])
                if existing:
                    self.add_or_update_document(**doc_info)
                    updated_docs += 1
                else:
                    self.add_or_update_document(**doc_info)
                    new_docs += 1
            
            processed += 1
            
            # Save periodically
            if processed % 10 == 0:
                self.save_data()
        
        # Final save
        self.save_data()
        
        print(f"\nScraping completed!")
        print(f"Total documents processed: {processed}")
        print(f"New documents added: {new_docs}")
        print(f"Documents updated: {updated_docs}")
        print(f"Total documents in database: {len(self.documents['documents'])}")

def main():
    parser = argparse.ArgumentParser(description="Scrape Vatican website for Pope Leo XIII documents")
    parser.add_argument("--output", "-o", default="pope_leo_documents.json", 
                       help="Output JSON file (default: pope_leo_documents.json)")
    parser.add_argument("--delay", "-d", type=float, default=1.0,
                       help="Delay between requests in seconds (default: 1.0)")
    
    args = parser.parse_args()
    
    scraper = VaticanScraper(data_file=args.output, delay=args.delay)
    scraper.scrape_all_documents()

if __name__ == "__main__":
    main()
