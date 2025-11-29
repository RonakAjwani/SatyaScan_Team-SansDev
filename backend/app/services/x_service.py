import os
import requests
import time
from typing import List, Dict, Optional

class XService:
    def __init__(self):
        self.bearer_token = os.getenv("X_BEARER_TOKEN")
        self.base_url = "https://api.twitter.com/2"

    def search_recent_tweets(self, query: str, max_results: int = 5) -> List[Dict]:
        """
        Search for recent tweets using X API v2.
        Returns a list of dictionaries containing tweet text and metadata.
        """
        if not self.bearer_token:
            print("X_BEARER_TOKEN not found. Skipping X search.")
            return []

        url = f"{self.base_url}/tweets/search/recent"
        
        # Truncate query to avoid 400 Bad Request (max 512 chars, but shorter is better for relevance)
        # Also remove newlines which can break the API
        safe_query = query.replace("\n", " ").strip()[:128]
        
        headers = {
            "Authorization": f"Bearer {self.bearer_token}",
            "User-Agent": "v2RecentSearchPython"
        }
        params = {
            "query": safe_query,
            "max_results": max(10, min(max_results, 100)), # Ensure between 10 and 100
            "tweet.fields": "created_at,author_id,public_metrics",
            "expansions": "author_id"
        }

        try:
            response = requests.get(url, headers=headers, params=params)
            
            if response.status_code == 429:
                print("X API Rate Limit Exceeded.")
                return []
            
            if response.status_code != 200:
                print(f"X API Error: {response.status_code} - {response.text}")
                return []

            json_response = response.json()
            data = json_response.get("data", [])
            includes = json_response.get("includes", {})
            users = {u["id"]: u for u in includes.get("users", [])}

            results = []
            for tweet in data:
                author_id = tweet.get("author_id")
                author = users.get(author_id, {})
                username = author.get("username", "unknown")
                
                results.append({
                    "text": tweet.get("text"),
                    "author": username,
                    "created_at": tweet.get("created_at"),
                    "url": f"https://x.com/{username}/status/{tweet.get('id')}",
                    "metrics": tweet.get("public_metrics", {})
                })
            
            return results

        except Exception as e:
            print(f"X Service Exception: {e}")
            return []

    def get_tweet_by_id(self, tweet_id: str) -> Dict:
        """
        Fetch a single tweet by ID.
        """
        if not self.bearer_token:
            return {}

        url = f"{self.base_url}/tweets/{tweet_id}"
        headers = {
            "Authorization": f"Bearer {self.bearer_token}",
            "User-Agent": "v2TweetLookupPython"
        }
        params = {
            "tweet.fields": "created_at,author_id,public_metrics",
            "expansions": "author_id"
        }

        try:
            response = requests.get(url, headers=headers, params=params)
            if response.status_code != 200:
                print(f"X API Error (Tweet Lookup): {response.status_code}")
                return {}

            json_response = response.json()
            data = json_response.get("data", {})
            includes = json_response.get("includes", {})
            users = {u["id"]: u for u in includes.get("users", [])}

            author_id = data.get("author_id")
            author = users.get(author_id, {})
            username = author.get("username", "unknown")

            return {
                "text": data.get("text"),
                "author": username,
                "created_at": data.get("created_at"),
                "url": f"https://x.com/{username}/status/{data.get('id')}",
                "metrics": data.get("public_metrics", {})
            }
        except Exception as e:
            print(f"X Service Exception (Tweet Lookup): {e}")
            return {}

x_service = XService()
