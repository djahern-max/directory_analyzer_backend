from sqlalchemy import Column, String, Integer, BigInteger, Boolean, Text, DateTime, ForeignKey
from sqlalchemy.sql.sqltypes import Numeric
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid

Base = declarative_base()

class Job(Base):
    __tablename__ = "jobs"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_name = Column(String(255), nullable=False)
    job_number = Column(String(50), nullable=False)
    directory_path = Column(Text, nullable=False, unique=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    total_pdf_files = Column(Integer, default=0)
    total_size_bytes = Column(BigInteger, default=0)
    status = Column(String(50), default='pending')  # pending, processing, completed, failed
    
    # Remove the circular foreign key - we'll track main contract differently
    main_contract_filename = Column(String(255), nullable=True)  # Just store the filename
    
    # Relationships
    documents = relationship("Document", back_populates="job", cascade="all, delete-orphan")

class Document(Base):
    __tablename__ = "documents"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id = Column(UUID(as_uuid=True), ForeignKey('jobs.id'), nullable=False)
    filename = Column(String(255), nullable=False)
    file_path = Column(Text, nullable=False)
    file_size_bytes = Column(BigInteger, nullable=False)
    file_size_kb = Column(Integer, nullable=False)
    file_size_mb = Column(Numeric(10, 2), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # File metadata
    file_hash = Column(String(64))  # MD5 hash for duplicate detection
    file_modified_time = Column(DateTime(timezone=True))
    is_accessible = Column(Boolean, default=True)
    
    # Relationships
    job = relationship("Job", back_populates="documents")
    text_extractions = relationship("TextExtraction", back_populates="document", cascade="all, delete-orphan")
    classifications = relationship("DocumentClassification", back_populates="document", cascade="all, delete-orphan")
    analysis_results = relationship("AnalysisResult", back_populates="document", cascade="all, delete-orphan")

class TextExtraction(Base):
    __tablename__ = "text_extractions"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id = Column(UUID(as_uuid=True), ForeignKey('documents.id'), nullable=False)
    extraction_method = Column(String(50), nullable=False)  # 'pdfplumber', 'google_vision', 'hybrid'
    extracted_text = Column(Text)
    text_length = Column(Integer, default=0)
    extraction_success = Column(Boolean, default=False)
    extraction_error = Column(Text)
    extraction_time_seconds = Column(Numeric(10, 3))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # OCR specific fields
    confidence_score = Column(Numeric(5, 2))  # For Google Vision OCR confidence
    page_count = Column(Integer)
    
    # Relationships
    document = relationship("Document", back_populates="text_extractions")

class DocumentClassification(Base):
    __tablename__ = "document_classifications"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id = Column(UUID(as_uuid=True), ForeignKey('documents.id'), nullable=False)
    classification_method = Column(String(50), default='claude_ai')  # 'claude_ai', 'manual', etc.
    
    # Classification results
    document_type = Column(String(50), default='UNKNOWN')
    importance = Column(String(20), default='MEDIUM')
    status = Column(String(50), default='UNKNOWN')
    confidence = Column(String(20), default='MEDIUM')
    summary = Column(Text)
    recommendation = Column(String(50), default='REVIEW_MANUALLY')
    
    # Extracted information
    key_parties = Column(Text)
    dollar_amount = Column(String(100))
    project_info = Column(Text)
    
    # AI metadata
    ai_model = Column(String(100))
    ai_tokens_used = Column(Integer)
    classification_time_seconds = Column(Numeric(10, 3))
    classification_error = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    document = relationship("Document", back_populates="classifications")

class AnalysisResult(Base):
    __tablename__ = "analysis_results"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id = Column(UUID(as_uuid=True), ForeignKey('documents.id'), nullable=False)
    job_id = Column(UUID(as_uuid=True), ForeignKey('jobs.id'), nullable=False)
    
    # Ranking and scoring
    importance_score = Column(Integer, default=0)
    rank = Column(Integer)
    priority_level = Column(String(50))
    is_main_contract = Column(Boolean, default=False)
    ranking_reason = Column(Text)
    
    # Analysis metadata
    analysis_date = Column(DateTime(timezone=True), server_default=func.now())
    analyzer_version = Column(String(50))
    
    # Relationships
    document = relationship("Document", back_populates="analysis_results")
    job = relationship("Job")

class AnalysisSession(Base):
    __tablename__ = "analysis_sessions"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id = Column(UUID(as_uuid=True), ForeignKey('jobs.id'), nullable=False)
    
    # Session metadata
    session_type = Column(String(50))  # 'full_analysis', 'main_contract_only'
    started_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True))
    status = Column(String(50), default='running')  # running, completed, failed
    
    # Results summary
    total_documents = Column(Integer, default=0)
    successful_extractions = Column(Integer, default=0)
    successful_classifications = Column(Integer, default=0)
    failed_files = Column(Text)  # JSON array of failed files
    
    # Performance metrics
    total_time_seconds = Column(Numeric(10, 3))
    estimated_cost = Column(Numeric(10, 4))
    
    # Error information
    error_message = Column(Text)
    error_details = Column(Text)  # JSON object with error details
