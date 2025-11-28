from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from backend.app.db.base import get_db
from backend.app.models.models import AnalysisRequest, Trend
from backend.app.core.agent import agent_app
import shutil
import os
import requests
from werkzeug.utils import secure_filename

router = APIRouter()

@router.post("/analyze")
async def analyze_content(
    text: str = Form(None),
    image_url: str = Form(None),
    embedded_tweets: list[str] = Form(None), # Accept list of tweet URLs
    file: UploadFile = File(None),
    db: AsyncSession = Depends(get_db)
):
    """
    Analyzes text or an image for misinformation.
    """
    if not text and not file:
        raise HTTPException(status_code=400, detail="Must provide either text or an image file.")

    # Handle File Upload
    image_bytes = None
    image_path = None # This will only be set if a file is uploaded

    # 1. Handle File Upload
    if file:
        upload_dir = "backend/uploads"
        os.makedirs(upload_dir, exist_ok=True)
        
        # Sanitize filename to prevent path traversal
        safe_filename = secure_filename(file.filename)
        # Ensure we don't overwrite existing files or just rely on unique IDs in real prod
        image_path = os.path.join(upload_dir, safe_filename)
        
        # Read bytes for memory processing
        image_bytes = await file.read()
        
        # Save to disk for record keeping
        with open(image_path, "wb") as buffer:
            buffer.write(image_bytes)
            
    # 2. Handle Image URL (from Page Scan)
    # 2. Handle Image URL (from Page Scan)
    elif image_url:
        try:
            # Add headers to mimic browser and avoid 401/403
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
            }
            resp = requests.get(image_url, headers=headers, timeout=10)
            if resp.status_code == 200:
                image_bytes = resp.content
            else:
                print(f"Warning: Failed to download image from URL: {resp.status_code}. Proceeding with text analysis only.")
                # Do not raise exception, just continue without image_bytes
                image_bytes = None
        except Exception as e:
            print(f"Warning: Failed to download image from URL: {e}. Proceeding with text analysis only.")
            image_bytes = None

    # Create Request Record
    db_request = AnalysisRequest(
        input_text=text[:500] if text else "Image Analysis", # Truncate text for DB if too long, or default for image analysis
        image_path=image_path, # image_path is only set if a file was uploaded
        status="processing"
    )
    db.add(db_request)
    await db.commit()
    await db.refresh(db_request)

    # Run Agent Workflow
    try:
        if image_bytes:
            # Use Image Analysis Agent
            from backend.app.core.image_agent import image_agent_app
            # If we have text AND image, we might want to pass both?
            # For now, let's prioritize the Image Agent but pass the text as context if needed.
            # The Image Agent expects 'ocr_text' but we can inject 'input_text' into the prompt.
            
            # TODO: Ideally, we should merge the agents. For now, let's run the Image Agent 
            # and maybe append the text analysis? 
            # Or better: The Image Agent is for "Forensics". 
            # The user wants to check if the image is AI generated.
            
            inputs = {"image_bytes": image_bytes}
            result = await image_agent_app.ainvoke(inputs)
            
            # If text was also provided, we might want to run the text agent too?
            # Complexity: High. Let's stick to Image Agent if image is present for now, 
            # as the user explicitly asked to scan the image "too".
            # But wait, if they scan a page, they want the TEXT verified AND the image checked.
            
            # Let's run Text Agent if text is present
            text_result = {}
            if text and len(text) > 50: # Only run text agent if substantial text is provided
                 inputs_text = {"input_text": text}
                 text_result = await agent_app.ainvoke(inputs_text)
            
            # Combine Results
            final_report = result["final_report"]
            text_report_content = text_result.get("final_report", "")
            
            if text_report_content:
                final_report += "\n\n--- TEXT VERIFICATION ---\n" + text_report_content
                
            # Merge verdicts logic
            text_is_misinfo = text_result.get("is_misinformation", False)
            image_is_misinfo = result.get("is_misinformation", False)
            
            # Default to text verdict if available, as it's usually more definitive for news
            is_misinfo = text_is_misinfo
            
            # If text is verified (not misinfo) but image is fake, we shouldn't mark the whole thing as fake news
            # unless the image is the primary content.
            if not text_is_misinfo and image_is_misinfo:
                # Check confidence. If image confidence is super high (>90), maybe flag it?
                # For now, let's keep is_misinfo=False (Verified) but the report will show the image warning.
                # Or better: use a new status "mixed"? The UI only supports boolean.
                # Let's trust the Text Agent for the overall "News Verdict".
                pass
            elif text_is_misinfo:
                is_misinfo = True
                
            # Confidence: Weighted average
            if text_result:
                # Give more weight to text analysis for news articles
                confidence = (text_result.get("confidence_score", 0) * 0.7) + (result.get("confidence_score", 0) * 0.3)
            else:
                confidence = result.get("confidence_score", 0)
            
            # Ensure strict rounding
            confidence = round(confidence, 2)
            
            citations = text_result.get("citations", []) # Prioritize text citations if available

            return {
                "id": db_request.id,
                "status": "completed",
                "verdict": is_misinfo,
                "confidence": confidence,
                "report": final_report, # Legacy support
                "image_report": result["final_report"],
                "text_report": text_report_content,
                "citations": citations
            }

        else:
            # Use Text Analysis Agent
            inputs = {
                "input_text": text or "",
                "embedded_tweets": embedded_tweets or []
            }
            result = await agent_app.ainvoke(inputs)
            final_report = result["final_report"]
            is_misinfo = result.get("is_misinformation", False)
            confidence = result.get("confidence_score", 0.0)
            citations = result.get("citations", [])
            
            # Update DB
            db_request.result_text = final_report
            db_request.confidence_score = confidence
            db_request.is_misinformation = is_misinfo
            db_request.status = "completed"
            await db.commit()
            
            return {
                "id": db_request.id,
                "status": "completed",
                "verdict": is_misinfo,
                "confidence": confidence,
                "report": final_report,
                "image_report": None,
                "text_report": final_report,
                "citations": citations
            }
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"Agent failed: {e}")
        db_request.status = "failed"
        await db.commit()
        raise HTTPException(status_code=500, detail=str(e))


