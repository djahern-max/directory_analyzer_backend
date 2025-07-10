from pydantic import BaseModel, Field
from typing import Optional, List
from enum import Enum

from app.models.base import BaseAPIModel


class DocumentType(str, Enum):
    """Document type classifications"""
    PRIMARY_CONTRACT = "PRIMARY_CONTRACT"
    CHANGE_ORDER = "CHANGE_ORDER"
    LETTER_OF_INTENT = "LETTER_OF_INTENT"
    INSURANCE_DOCUMENT = "INSURANCE_DOCUMENT"
    SCHEDULE = "SCHEDULE"
    AMENDMENT = "AMENDMENT"
    PROPOSAL = "PROPOSAL"
    INVOICE = "INVOICE"
    CORRESPONDENCE = "CORRESPONDENCE"
    UNKNOWN = "UNKNOWN"
    ERROR = "ERROR"


class ImportanceLevel(str, Enum):
    """Document importance levels"""
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class DocumentStatus(str, Enum):
    """Document status classifications"""
    EXECUTED_SIGNED = "EXECUTED_SIGNED"
    DRAFT_UNSIGNED = "DRAFT_UNSIGNED"
    PROPOSAL = "PROPOSAL"
    EXPIRED = "EXPIRED"
    UNKNOWN = "UNKNOWN"


class ConfidenceLevel(str, Enum):
    """Confidence levels for classifications"""
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class Recommendation(str, Enum):
    """Analysis recommendations"""
    ANALYZE_FULLY = "ANALYZE_FULLY"
    REVIEW_MANUALLY = "REVIEW_MANUALLY"
    ARCHIVE = "ARCHIVE"
    SKIP = "SKIP"


class PriorityLevel(str, Enum):
    """Document priority levels"""
    MAIN_CONTRACT = "MAIN_CONTRACT"
    HIGH_PRIORITY = "HIGH_PRIORITY"
    ANALYZE_RECOMMENDED = "ANALYZE_RECOMMENDED"
    SUPPORTING_DOCUMENT = "SUPPORTING_DOCUMENT"


class DocumentClassification(BaseAPIModel):
    """Document classification result"""
    
    filename: str
    document_type: DocumentType = DocumentType.UNKNOWN
    importance: ImportanceLevel = ImportanceLevel.MEDIUM
    status: DocumentStatus = DocumentStatus.UNKNOWN
    confidence: ConfidenceLevel = ConfidenceLevel.MEDIUM
    summary: str = ""
    recommendation: Recommendation = Recommendation.REVIEW_MANUALLY
    
    # Additional extracted information
    key_parties: str = ""
    dollar_amount: str = "NONE"
    project_info: str = ""
    
    # File metadata
    file_path: str
    file_size_kb: int
    text_length: int
    
    # Analysis metadata
    classification_date: str
    error: Optional[str] = None
    
    # Allow extra fields that might come from the AI service
    ai_model: Optional[str] = None
    total_documents_analyzed: Optional[int] = None


class RankedDocument(DocumentClassification):
    """Document with ranking information"""
    
    rank: int = Field(description="Document rank (1 = highest importance)")
    importance_score: int = Field(description="Calculated importance score")
    priority_level: PriorityLevel = PriorityLevel.SUPPORTING_DOCUMENT
    is_main_contract: bool = False
    ranking_reason: Optional[str] = Field(
        None, 
        description="Explanation for why this ranking was assigned"
    )


class MainContractInfo(BaseAPIModel):
    """Information about the identified main contract"""
    
    filename: str
    file_path: str
    importance_score: int
    ranking_reason: str
    document_type: DocumentType
    summary: str
    confidence: ConfidenceLevel
    
    # Add the missing rank field
    rank: int = 1
    
    # Allow extra fields
    ai_model: Optional[str] = None
    total_documents_analyzed: Optional[int] = None


class ClassificationSummary(BaseAPIModel):
    """Summary of document classifications"""
    
    total_documents: int
    by_type: dict = Field(description="Count of documents by type")
    by_importance: dict = Field(description="Count of documents by importance")
    by_status: dict = Field(description="Count of documents by status")
    recommendations: dict = Field(description="Count of documents by recommendation")
