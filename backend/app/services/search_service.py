import os
from dotenv import load_dotenv
import pathlib

# Try to find .env file
env_path = pathlib.Path("backend/.env")
if not env_path.exists():
    env_path = pathlib.Path(__file__).parent.parent.parent / ".env"

load_dotenv(dotenv_path=env_path)
import requests
from typing import List, Dict, Any
from tavily import TavilyClient

class SearchService:
    def __init__(self):
        self.tavily_key = os.getenv("TAVILY_API_KEY")
        self.serper_key = os.getenv("SERPER_API_KEY")
        self.google_key = os.getenv("GOOGLE_API_KEY")
        self.google_cse_id = os.getenv("GOOGLE_CSE_ID")

        self.tavily_client = TavilyClient(api_key=self.tavily_key) if self.tavily_key else None
    
    def search(self, query: str, max_results: int = 5) -> List[Dict[str, Any]]:
        """
        Unified search method.
        Prioritizes Tavily -> Serper -> Google Custom Search -> Mock Fallback.
        Returns a list of dicts: [{'title': ..., 'url': ..., 'content': ...}]
        """
        results = []

        # 1. Try Tavily
        if self.tavily_client:
            try:
                response = self.tavily_client.search(query, max_results=max_results)
                results = response.get("results", [])
                if results:
                    return results
            except Exception as e:
                print(f"Tavily search failed: {e}")

        # 2. Try Serper
        if self.serper_key:
            try:
                results = self._search_serper(query, max_results)
                if results:
                    return results
            except Exception as e:
                print(f"Serper search failed: {e}")

        # 3. Try Google Custom Search
        if self.google_key and self.google_cse_id:
            try:
                results = self._search_google(query, max_results)
                if results:
                    return results
            except Exception as e:
                print(f"Google search failed: {e}")
        
        # 4. Fallback / Mock
        return self._mock_search(query)

    def _search_serper(self, query: str, max_results: int) -> List[Dict[str, Any]]:
        url = "https://google.serper.dev/search"
        payload = {"q": query, "num": max_results}
        headers = {
            "X-API-KEY": self.serper_key,
            "Content-Type": "application/json"
        }
        response = requests.post(url, headers=headers, json=payload)
        response.raise_for_status()
        data = response.json()
        
        # Standardize format
        return [
            {
                "title": item.get("title"),
                "url": item.get("link"),
                "content": item.get("snippet")
            }
            for item in data.get("organic", [])
        ]

    def _search_google(self, query: str, max_results: int) -> List[Dict[str, Any]]:
        url = "https://www.googleapis.com/customsearch/v1"
        params = {
            "key": self.google_key,
            "cx": self.google_cse_id,
            "q": query,
            "num": max_results
        }
        response = requests.get(url, params=params)
        response.raise_for_status()
        data = response.json()
        
        return [
            {
                "title": item.get("title"),
                "url": item.get("link"),
                "content": item.get("snippet")
            }
            for item in data.get("items", [])
        ]

    def _mock_search(self, query: str) -> List[Dict[str, Any]]:
        """Mock results for testing when keys are missing."""
        return [
            {
                "title": f"Search Result for {query}",
                "url": "http://example.com",
                "content": f"This is a mock search result content for query: {query}. It claims that X is true."
            },
            {
                "title": f"Debunking {query}",
                "url": "http://factcheck.org/example",
                "content": f"This is a mock fact check. The claim in {query} is mostly FALSE."
            }
        ]

    def fact_check_search(self, query: str) -> List[Dict[str, Any]]:
        """
        Queries Google Fact Check Tools API for existing fact checks.
        """
        if not self.google_key:
            return []
            
        url = "https://factchecktools.googleapis.com/v1alpha1/claims:search"
        params = {
            "key": self.google_key,
            "query": query,
            "pageSize": 3
        }
        
        try:
            response = requests.get(url, params=params)
            if response.status_code != 200:
                print(f"Fact Check API Error: {response.status_code} - {response.text}")
                return []
                
            data = response.json()
            claims = data.get("claims", [])
            
            results = []
            for claim in claims:
                text = claim.get("text", "")
                claimant = claim.get("claimant", "Unknown")
                claim_date = claim.get("claimDate", "")
                
                for review in claim.get("claimReview", []):
                    publisher = review.get("publisher", {}).get("name", "Unknown")
                    url = review.get("url", "")
                    title = review.get("title", "")
                    rating = review.get("textualRating", "Unknown")
                    
                    content = f"[FACT CHECK] Claim: '{text}' by {claimant} ({claim_date}). Verdict by {publisher}: {rating}. Source: {url}"
                    
                    results.append({
                        "title": f"Fact Check: {title or text}",
                        "url": url,
                        "content": content,
                        "source": "google_fact_check",
                        "is_fact_check": True
                    })
            
            return results
            
        except Exception as e:
            print(f"Fact Check API Exception: {e}")
            return []

search_service = SearchService()
