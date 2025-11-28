import os
from dotenv import load_dotenv
import pathlib

# Try to find .env file
# Option 1: Relative to CWD (if running from root)
env_path = pathlib.Path("backend/.env")
if not env_path.exists():
    # Option 2: Relative to this file (if running differently)
    env_path = pathlib.Path(__file__).parent.parent.parent / ".env"

load_dotenv(dotenv_path=env_path)
import operator
from typing import Annotated, List, Dict, TypedDict, Union

from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage, BaseMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langgraph.graph import StateGraph, END

from backend.app.services.search_service import search_service
from backend.app.services.ocr_service import OCRService
from backend.app.services.x_service import x_service
from backend.app.core.scoring import ConfidenceCalculator

# Initialize Calculator
confidence_calculator = ConfidenceCalculator()

# --- Configuration ---
CEREBRAS_API_KEY = os.getenv("CEREBRAS_API_KEY")
# If Cerebras key is missing, we can fallback to a mock or raise error in production.
# Using ChatOpenAI client pointed to Cerebras base URL.
LLM_MODEL = "llama-3.3-70b"

if CEREBRAS_API_KEY:
    llm = ChatOpenAI(
        api_key=CEREBRAS_API_KEY,
        base_url="https://api.cerebras.ai/v1",
        model=LLM_MODEL,
        temperature=0.1
    )
else:
    # Fallback to standard OpenAI if key is set, or a Mock for testing structure
    # This ensures the code runs even if the user hasn't pasted the key yet.
    print("WARNING: CEREBRAS_API_KEY not found. Using Mock LLM.")
    # In newer langchain versions, FakeListLLM might be moved or requires langchain-community
    # We'll just use the standard ChatOpenAI with a mock key and expect it to fail or use it only if keys are provided later.
    # Ideally, we'd use a Mock object for unit tests.
    llm = ChatOpenAI(api_key="mock", base_url="https://api.cerebras.ai/v1", model=LLM_MODEL)


# --- State Definition ---
class AgentState(TypedDict):
    input_text: str
    image_bytes: Union[bytes, None]
    embedded_tweets: List[str] # List of Tweet URLs
    
    # Internal State
    extracted_claims: List[str]
    search_queries: List[str]
    evidence: List[Dict]
    verification_notes: str
    
    # Final Output
    final_report: str
    confidence_score: float
    is_misinformation: bool

# --- Nodes ---

def input_processor(state: AgentState):
    """
    Node 1: Handles OCR if image is present.
    """
    text = state.get("input_text", "")
    image_data = state.get("image_bytes")
    
    if image_data:
        ocr_text = OCRService.extract_text(image_data)
        if ocr_text:
            text += f"\n\n[Extracted Text from Image]:\n{ocr_text}"
        else:
            text += "\n\n[Image Processing]: No text detected or OCR failed."
    
    # Handle Embedded Tweets
    embedded_tweets = state.get("embedded_tweets", [])
    if embedded_tweets:
        print(f"DEBUG: Processing {len(embedded_tweets)} embedded tweets...")
        for tweet_url in embedded_tweets:
            try:
                # Extract ID from URL (e.g. .../status/123456)
                tweet_id = tweet_url.split("/status/")[-1].split("?")[0]
                tweet_data = x_service.get_tweet_by_id(tweet_id)
                if tweet_data:
                    text += f"\n\n[Embedded X Post by @{tweet_data['author']}]:\n{tweet_data['text']}\n(Date: {tweet_data['created_at']})"
            except Exception as e:
                print(f"Failed to process embedded tweet {tweet_url}: {e}")

    return {"input_text": text}

def claim_extractor(state: AgentState):
    """
    Node 2: Analyze text to extract verifiable claims.
    """
    messages = [
        SystemMessage(content="""You are an expert fact-checker. Your goal is to identify verifiable factual claims.
        
        RULES:
        1. Ignore opinions, predictions, or subjective statements.
        2. Extract only specific, checkable facts (dates, numbers, events, quotes).
        3. If the text is pure opinion or vague, return "NO_CLAIMS".
        4. Return the claims as a bulleted list.
        """),
        HumanMessage(content=state["input_text"])
    ]
    try:
        response = llm.invoke(messages)
    except Exception as e:
        print(f"LLM Invoke Failed in Claim Extractor: {e}")
        raise e
    
    if "NO_CLAIMS" in response.content:
        return {"extracted_claims": []}
        
    return {"extracted_claims": [response.content]}

from backend.app.services.scraper_service import scraper_service

# ... (imports)

def researcher(state: AgentState):
    """
    Node 3: Generate search queries and fetch evidence.
    """
    claims_list = state.get("extracted_claims", [])
    if not claims_list:
        return {"search_queries": [], "evidence": []}
        
    claims = claims_list[0]
    
    print(f"DEBUG: Researcher Node Started. Claims: {claims[:50]}...")
    
    # 1. Generate Queries
    query_gen_prompt = f"Given these claims:\n{claims}\n\nGenerate 3 specific search queries to verify them. If the claims are about a specific country (e.g., India), include queries targeting reputable local news sources (e.g., 'site:ndtv.com', 'site:thehindu.com', 'site:indianexpress.com'). Return only the queries, one per line."
    queries_response = llm.invoke([HumanMessage(content=query_gen_prompt)])
    queries = queries_response.content.split('\n')
    queries = [q.strip() for q in queries if q.strip()]
    print(f"DEBUG: Generated Queries: {queries}")
    
    all_evidence = []

    # 1.1 Try Google Fact Check API First (High Priority)
    try:
        print("DEBUG: Calling Fact Check API...")
        fact_check_results = search_service.fact_check_search(claims)
        print(f"DEBUG: Fact Check Results: {len(fact_check_results)}")
        if fact_check_results:
            all_evidence.extend(fact_check_results)
            # If we found direct fact checks, we might not need as many general searches
            # But let's keep one general search for context
            queries = queries[:1] 
    except Exception as e:
        print(f"Fact Check Search failed: {e}")

    # 2. Execute Web Search
    print("DEBUG: Executing Web Search...")
    for q in queries:
        try:
            results = search_service.search(q, max_results=2)
            all_evidence.extend(results)
        except Exception as e:
            print(f"DEBUG: Web Search failed for query '{q}': {e}")
    
    # 2.1 Execute X Search (Social Context)
    try:
        print("DEBUG: Executing X Search...")
        # Use the first generated query for X search to avoid length limits and improve relevance
        x_query = queries[0] if queries else claims[:100] 
        x_results = x_service.search_recent_tweets(x_query, max_results=5)
        for tweet in x_results:
            all_evidence.append({
                "url": tweet['url'],
                "content": f"[X/Twitter Post by @{tweet['author']}]: {tweet['text']} (Likes: {tweet['metrics'].get('like_count', 0)})",
                "source": "x.com"
            })
    except Exception as e:
        print(f"X Search failed: {e}")

    # 3. Scrape Full Content for Top Results
    print("DEBUG: Scraping Content...")
    # Limit to top 3 unique URLs to save time (excluding X urls which are already full text)
    unique_evidence = {e['url']: e for e in all_evidence}.values()
    
    final_evidence = []
    for e in unique_evidence:
        if e.get("source") == "x.com" or e.get("is_fact_check", False):
            final_evidence.append(e)
            continue
            
        if len(final_evidence) >= 5: # Increased limit to accommodate fact checks
            continue

        try:
            full_text = scraper_service.scrape_url(e['url'])
            if full_text:
                e['content'] = full_text # Replace snippet with full text
        except Exception as e:
             print(f"DEBUG: Scraping failed for {e['url']}: {e}")
             
        final_evidence.append(e)
        
    print(f"DEBUG: Researcher Node Finished. Evidence count: {len(final_evidence)}")
    return {"search_queries": queries, "evidence": final_evidence}

def fact_checker(state: AgentState):
    """
    Node 4: Verify claims against evidence.
    """
    claims_list = state.get("extracted_claims", [])
    if not claims_list:
        return {"verification_notes": "No factual claims were identified in the input text. Therefore, no verification was performed."}
        
    claims = claims_list[0]
    evidence = state.get("evidence", [])
    input_text = state.get("input_text", "")
    
    # Use input text as context if no external evidence found, but warn about it
    if not evidence and not input_text:
         return {"verification_notes": "No evidence could be found for the identified claims. Verdict: UNVERIFIED."}
    
    evidence_text = "\n\n".join([f"Source: {e['url']}\nContent: {e['content'][:4000]}" for e in evidence]) # Limit context per source
    
    prompt = f"""
    Analyze the following claims against the provided evidence.
    
    CLAIMS:
    {claims}
    
    EVIDENCE:
    {evidence_text}
    
    SOURCE CONTEXT (The article being analyzed):
    {input_text[:5000]}
    
    INSTRUCTIONS:
    1. For each claim, determine if it is TRUE, FALSE, or MISLEADING based on the EVIDENCE and SOURCE CONTEXT.
    2. CAUTION WITH TRUSTED SOURCES: Even if a reputable source (like Times of India, NDTV) reports an event, do NOT treat it as absolute fact if it is the ONLY source.
       - If only one source reports it: Verdict should be "LIKELY TRUE" or "REPORTED BY [SOURCE]".
       - Explanation must state: "Reported by [Source], but not independently verified by others."
    3. EXCEPTION: If multiple reputable regional sources confirm it, or if there is direct primary evidence (like an embedded video/tweet proving the statement), you may mark it as TRUE.
    4. DIRECT EVIDENCE: Embedded X Posts are primary evidence of *what was said*, but verify the *content* of the statement independently if possible.
    5. You MUST cite the Source URL for every verification decision.
    6. Be strict. Do not assume facts not present in the evidence.
    
    OUTPUT FORMAT:
    - Verdict: [TRUE / FALSE / MISLEADING / UNVERIFIED]
    - Confidence: [0-100]
    - Explanation: [Reasoning with specific citations]
    """
    
    response = llm.invoke([HumanMessage(content=prompt)])
    return {"verification_notes": response.content}

def synthesizer(state: AgentState):
    """
    Node 5: Generate final user-facing report.
    """
    print("DEBUG: Synthesizer Node Started.")
    notes = state["verification_notes"]
    
    prompt = f"""
    Based on the verification notes below, write a helpful, accessible response for a general audience.
    
    NOTES:
    {notes}
    
    INSTRUCTIONS:
    1. Start with a clear verdict: "Verified", "False", "Misleading", or "Unverified".
    2. If Unverified, clearly state that there isn't enough reliable information yet.
    3. Explain the reasoning simply, citing the sources mentioned in the notes.
    4. Keep it concise (under 200 words).
    """
    
    try:
        response = llm.invoke([HumanMessage(content=prompt)])
    except Exception as e:
        print(f"LLM Invoke Failed in Synthesizer: {e}")
        raise e
    
    # Simple heuristic parsing for score/bool
    notes_upper = notes.upper()
    is_misinfo = "FALSE" in notes_upper or "MISLEADING" in notes_upper
    
    # Calculate Confidence Score
    # We estimate LLM certainty based on keywords if not provided explicitly
    llm_certainty = 90.0 if "TRUE" in notes_upper or "FALSE" in notes_upper else 50.0
    
    # Get claims and evidence from state
    claims_list = state.get("extracted_claims", [])
    claim_text = claims_list[0] if claims_list else ""
    evidence = state.get("evidence", [])
    
    print(f"DEBUG: Calculating Confidence. Evidence count: {len(evidence)}")
    try:
        confidence = confidence_calculator.calculate_confidence(
            claim=claim_text,
            evidence=evidence,
            llm_confidence=llm_certainty
        )
        print(f"DEBUG: Confidence Score: {confidence}")
    except Exception as e:
        print(f"DEBUG: Confidence Calculation Failed: {e}")
        confidence = 0.0
    
    # Extract Citations
    citations = [e.get('url') for e in evidence if e.get('url')]
    
    print("DEBUG: Synthesizer Node Finished.")
    return {
        "final_report": response.content,
        "is_misinformation": is_misinfo,
        "confidence_score": confidence,
        "citations": citations
    }

# --- Graph Construction ---

workflow = StateGraph(AgentState)

workflow.add_node("input_processor", input_processor)
workflow.add_node("claim_extractor", claim_extractor)
workflow.add_node("researcher", researcher)
workflow.add_node("fact_checker", fact_checker)
workflow.add_node("synthesizer", synthesizer)

workflow.set_entry_point("input_processor")

workflow.add_edge("input_processor", "claim_extractor")
workflow.add_edge("claim_extractor", "researcher")
workflow.add_edge("researcher", "fact_checker")
workflow.add_edge("fact_checker", "synthesizer")
workflow.add_edge("synthesizer", END)

agent_app = workflow.compile()
