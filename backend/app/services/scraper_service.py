import requests
from bs4 import BeautifulSoup
import logging

logger = logging.getLogger(__name__)

class ScraperService:
    @staticmethod
    def scrape_url(url: str, timeout: int = 5) -> str:
        """
        Fetches the full text content of a URL.
        """
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
            }
            response = requests.get(url, headers=headers, timeout=timeout)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Remove script and style elements
            for script in soup(["script", "style", "nav", "footer", "header"]):
                script.decompose()
                
            # Get text
            text = soup.get_text(separator=' ', strip=True)
            
            # Basic cleaning: collapse multiple spaces
            text = ' '.join(text.split())
            
            # Limit length to avoid context window overflow (e.g., 10k chars)
            return text[:10000]
            
        except Exception as e:
            logger.warning(f"Scraping failed for {url}: {e}")
            return ""

scraper_service = ScraperService()
