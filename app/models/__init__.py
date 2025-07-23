from .database import (
    Base,
    User,
    Job,
    Contract,
    ContractRelationship,
    TextExtraction,
    DocumentClassification,
    AnalysisSession,
    AnalysisResult,
    UsageRecord,
    ChatMessage,  # Add this line
    ContractType,
    StorageLocation,
)

__all__ = [
    "Base",
    "User",
    "Job",
    "Contract",
    "ContractRelationship",
    "TextExtraction",
    "DocumentClassification",
    "AnalysisSession",
    "AnalysisResult",
    "UsageRecord",
    "ChatMessage",  # Add this line
    "ContractType",
    "StorageLocation",
]
