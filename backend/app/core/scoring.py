import re
from typing import List, Dict
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np

class ConfidenceCalculator:
    def __init__(self):
        # Domain Trust Lists
        self.high_trust_domains = [
            # Global / US High Trust
            ".gov", ".edu", "reuters.com", "apnews.com", "bbc.com", "npr.org", 
            "pbs.org", "nytimes.com", "washingtonpost.com", "wsj.com", "bloomberg.com",
            "snopes.com", "factcheck.org", "politifact.com",
            
            # Global Crisis / Health / Climate
            "who.int", "un.org", "cdc.gov", "nasa.gov", "ipcc.ch", "redcross.org", 
            "amnesty.org", "hrw.org", "weforum.org",

            # Indian High Trust & Fact Checkers
            "altnews.in", "boomlive.in", "quint.com", "newslaundry.com", # Fact checkers/Indep
            "ndtv.com", "thehindu.com", "indianexpress.com", "livemint.com", 
            "business-standard.com", "theprint.in", "scroll.in", "ptinews.com",
            "thewire.in", "deccanherald.com"
        ]
        self.medium_trust_domains = [
            # Global Medium
            "cnn.com", "foxnews.com", "msnbc.com", "abcnews.go.com", "nbcnews.com",
            "cbsnews.com", "usatoday.com", "theguardian.com", "aljazeera.com",
            "dw.com", "france24.com",
            
            # Indian Medium (Mainstream/Commercial)
            "timesofindia.indiatimes.com", "hindustantimes.com", "indiatoday.in", 
            "news18.com", "firstpost.com", "zeenews.india.com", "wionews.com",
            "dnaindia.com", "outlookindia.com", "economictimes.indiatimes.com"
        ]
        # Low trust is implicit (anything else)

    def calculate_confidence(self, claim: str, evidence: List[Dict], llm_confidence: float = 0.0) -> float:
        """
        Calculates a hybrid confidence score (0-100).
        Formula: (Relevance * 0.4) + (Source_Trust * 0.4) + (LLM_Confidence * 0.2)
        """
        if not evidence:
            return 0.0

        # 1. Calculate Semantic Relevance (TF-IDF Cosine Similarity)
        relevance_score = self._calculate_relevance(claim, evidence)
        
        # 2. Calculate Source Trust Score
        source_score = self._calculate_source_trust(evidence)
        
        # 3. Weighted Combination
        raw_score = (relevance_score * 0.4) + (source_score * 0.4) + (llm_confidence * 0.2)
        
        # 4. Penalties & Adjustments
        # Penalty for low evidence count (Relaxed)
        # Skip penalty if we have a High Trust source (source_score >= 90)
        if len(evidence) < 2 and source_score < 90:
            raw_score *= 0.90  # 10% penalty only if very low evidence AND not high trust
            
        # Dampening to prevent unrealistic 100%
        # Cap at 98% unless it's absolutely perfect (rare)
        final_score = min(raw_score, 98.0)
        
        return float(f"{final_score:.2f}")

    def _calculate_relevance(self, claim: str, evidence: List[Dict]) -> float:
        """
        Uses TF-IDF to find how relevant the evidence text is to the claim.
        Returns 0-100.
        """
        try:
            evidence_texts = [e.get('content', '') for e in evidence]
            if not evidence_texts:
                return 0.0
            
            # Combine all evidence into one document for comparison, or compare individually?
            # Let's compare claim vs. each evidence snippet and take the max similarity.
            
            documents = [claim] + evidence_texts
            tfidf_vectorizer = TfidfVectorizer().fit_transform(documents)
            cosine_similarities = cosine_similarity(tfidf_vectorizer[0:1], tfidf_vectorizer[1:]).flatten()
            
            # We take the maximum similarity found in any evidence snippet
            max_similarity = np.max(cosine_similarities)
            
            # Scale 0-1 to 0-100
            return max_similarity * 100.0
        except Exception as e:
            print(f"Error calculating relevance: {e}")
            return 50.0 # Fallback

    def _calculate_source_trust(self, evidence: List[Dict]) -> float:
        """
        Scoring based on domain reputation.
        High Trust = 100
        Medium Trust = 70
        Unknown/Low = 30
        Returns average trust score of all evidence.
        """
        total_score = 0
        count = 0
        
        for e in evidence:
            url = e.get('url', '').lower()
            score = 30 # Default low/unknown
            
            # Check High Trust
            if any(d in url for d in self.high_trust_domains):
                score = 100
            # Check Medium Trust
            elif any(d in url for d in self.medium_trust_domains):
                score = 70
                
            total_score += score
            count += 1
            
        if count == 0:
            return 0.0
            
        return total_score / count
