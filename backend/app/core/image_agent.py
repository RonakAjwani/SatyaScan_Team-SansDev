import os
from typing import TypedDict, Union, List, Dict
from langgraph.graph import StateGraph, END
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from backend.app.services.ocr_service import OCRService
from backend.app.services.forensic_service import forensic_service
from backend.app.core.agent import llm  # Reuse the LLM configuration from the main agent

# --- State Definition ---
class ImageAgentState(TypedDict):
    image_bytes: bytes
    
    # Analysis Results
    ocr_text: str
    metadata_result: Dict
    forensic_result: Dict
    
    # Final Output
    final_report: str
    verdict: str # "REAL", "FAKE", "MANIPULATED", "UNKNOWN"
    confidence_score: float
    is_misinformation: bool

# --- Nodes ---

def ocr_node(state: ImageAgentState):
    """Extracts text from the image."""
    text = OCRService.extract_text(state["image_bytes"])
    return {"ocr_text": text}

def metadata_node(state: ImageAgentState):
    """Extracts metadata and checks for AI signatures."""
    result = forensic_service.extract_metadata(state["image_bytes"])
    return {"metadata_result": result}

def forensic_node(state: ImageAgentState):
    """Performs ELA and other forensic checks."""
    ela_result = forensic_service.perform_ela(state["image_bytes"])
    gan_result = forensic_service.analyze_frequency_spectrum(state["image_bytes"])
    
    # Merge results
    return {"forensic_result": {**ela_result, **gan_result}}

def synthesizer_node(state: ImageAgentState):
    """Synthesizes all signals into a final verdict."""
    ocr = state.get("ocr_text", "")
    meta = state.get("metadata_result", {})
    forensics = state.get("forensic_result", {})
    
    prompt = f"""
    Analyze the following forensic data for an image to determine if it is AI-generated, manipulated, or authentic.
    
    1. OCR TEXT (Content):
    "{ocr[:1000]}"
    
    2. METADATA ANALYSIS:
    - Software: {meta.get('software', 'N/A')}
    - AI Keywords Found: {meta.get('is_ai_generated', False)}
    - Edited Keywords Found: {meta.get('is_edited', False)}
    
    3. FORENSIC ANALYSIS:
    - ELA Score (0-100, >50 suggests manipulation): {forensics.get('ela_score', 0)}
    - Max Difference: {forensics.get('max_diff', 0)}
    - GAN Artifact Score (0-100, >70 suggests AI): {forensics.get('gan_score', 0)}
    - Spectral Mean: {forensics.get('spectral_mean', 0)}
    - Spectral Std Dev: {forensics.get('spectral_std', 0)}
    
    INSTRUCTIONS:
    - Determine the VERDICT: [REAL / FAKE / MANIPULATED / UNKNOWN]
    - FAKE = Clear AI generation signatures OR High GAN Artifact Score (>70) with abnormal spectral variance.
    - MANIPULATED = High ELA score or "Photoshop" in metadata.
    - REAL = No signs of tampering.
    - UNKNOWN = Insufficient data.
    
    - Provide a CONFIDENCE SCORE (0-100).
    - Write a short REPORT explaining the findings in SIMPLE, LAYMAN TERMS.
      - STRICTLY FORBIDDEN: Do not use words like "ELA", "GAN", "Spectral Variance", "Error Level Analysis", "Frequency Spectrum".
      - Instead of "High ELA Score", say "Inconsistencies in the image quality suggest editing."
      - Instead of "High GAN Score", say "The image contains patterns typical of AI generation."
      - Focus on *what* the user needs to know: Is it real? Is it fake? Why?
      - Keep it under 3 sentences.
    
    OUTPUT FORMAT:
    Verdict: [VERDICT]
    Confidence: [SCORE]
    Report: [Simple Explanation]
    """
    
    response = llm.invoke([HumanMessage(content=prompt)])
    content = response.content
    
    # Simple parsing
    verdict = "UNKNOWN"
    if "FAKE" in content.upper(): verdict = "FAKE"
    elif "MANIPULATED" in content.upper(): verdict = "MANIPULATED"
    elif "REAL" in content.upper(): verdict = "REAL"
    
    # Extract confidence (heuristic)
    import re
    confidence_match = re.search(r"Confidence:\s*(\d+)", content)
    confidence = float(confidence_match.group(1)) if confidence_match else 50.0
    
    # Determine is_misinformation flag (for UI badge)
    is_misinfo = verdict in ["FAKE", "MANIPULATED"]
    
    return {
        "final_report": content,
        "verdict": verdict,
        "confidence_score": confidence,
        "is_misinformation": is_misinfo
    }

# --- Graph Construction ---
workflow = StateGraph(ImageAgentState)

workflow.add_node("ocr_node", ocr_node)
workflow.add_node("metadata_node", metadata_node)
workflow.add_node("forensic_node", forensic_node)
workflow.add_node("synthesizer", synthesizer_node)

# Parallel Execution
workflow.set_entry_point("ocr_node")
workflow.add_edge("ocr_node", "metadata_node") # Sequential for now to simplify graph, can be parallel
workflow.add_edge("metadata_node", "forensic_node")
workflow.add_edge("forensic_node", "synthesizer")
workflow.add_edge("synthesizer", END)

image_agent_app = workflow.compile()
