from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, Float, ForeignKey, Boolean
from sqlalchemy.orm import relationship
from backend.app.db.base import Base

class AnalysisRequest(Base):
    __tablename__ = "analysis_requests"

    id = Column(Integer, primary_key=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Input
    input_text = Column(Text, nullable=True)
    image_path = Column(String, nullable=True)
    source_url = Column(String, nullable=True)  # If it came from a specific URL
    
    # Output
    status = Column(String, default="pending")  # pending, processing, completed, failed
    result_text = Column(Text, nullable=True)   # The final explanation
    confidence_score = Column(Float, nullable=True) # 0.0 to 1.0 (or 0-100)
    is_misinformation = Column(Boolean, nullable=True)
    
    sources = relationship("Source", back_populates="analysis_request")


class Trend(Base):
    __tablename__ = "trends"

    id = Column(Integer, primary_key=True, index=True)
    detected_at = Column(DateTime, default=datetime.utcnow)
    topic = Column(String, index=True)
    description = Column(Text)
    source_stream = Column(String) # e.g., "RSS", "Reddit"
    url = Column(String, nullable=True)
    
    # Analysis of the trend
    is_verified = Column(Boolean, default=False)
    verification_result = Column(Text, nullable=True)


class Source(Base):
    __tablename__ = "sources"

    id = Column(Integer, primary_key=True, index=True)
    analysis_request_id = Column(Integer, ForeignKey("analysis_requests.id"))
    url = Column(String)
    title = Column(String, nullable=True)
    snippet = Column(Text, nullable=True)
    credibility_score = Column(Float, nullable=True) # AI's rating of this source
    
    analysis_request = relationship("AnalysisRequest", back_populates="sources")
