# app/api/document_chat.py
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
from datetime import datetime
import logging
from sqlalchemy.orm import Session

from app.middleware.premium_check import verify_premium_subscription
from app.core.exceptions import DirectoryAnalyzerException
from app.services.document_chat_service import DocumentChatService
from app.config import settings
from app.core.database import get_db
from app.api.deps import get_api_key

router = APIRouter(prefix="/documents", tags=["document-chat"])
logger = logging.getLogger("app.api.document_chat")


# Request/Response Models
class ChatMessage(BaseModel):
    role: str = Field(..., description="user or assistant")
    content: str = Field(..., description="Message content")
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class DocumentChatRequest(BaseModel):
    job_number: str = Field(..., description="Job number for the document")
    document_id: str = Field(..., description="Document identifier")
    message: str = Field(..., description="User's question about the document")
    chat_history: List[ChatMessage] = Field(
        default=[], description="Previous chat messages"
    )


class DocumentChatResponse(BaseModel):
    success: bool = True
    message: str
    document_info: Dict[str, Any]
    response_source: str = Field(
        description="Which document(s) the response is based on"
    )
    confidence: str = Field(description="HIGH, MEDIUM, LOW")
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class DocumentLoadRequest(BaseModel):
    job_number: str = Field(..., description="Job number")
    document_id: str = Field(..., description="Document identifier or filename")


class DocumentLoadResponse(BaseModel):
    success: bool = True
    document_info: Dict[str, Any]
    document_text: str = Field(description="Full extracted document text")
    analysis_summary: Dict[str, Any] = Field(
        description="AI-generated document summary"
    )
    suggested_questions: List[str] = Field(
        description="Suggested questions about this document"
    )


class DocumentChatHistoryRequest(BaseModel):
    job_number: str = Field(..., description="Job number")
    document_id: str = Field(..., description="Document identifier or filename")
    hours_back: Optional[int] = Field(
        24, description="Number of hours back to retrieve messages (default: 24)"
    )


@router.post("/load", response_model=DocumentLoadResponse)
async def load_document(
    request: DocumentLoadRequest,
    user: dict = Depends(verify_premium_subscription),
    db: Session = Depends(get_db),
    api_key: str = Depends(get_api_key),
):
    """Load a specific document for chat analysis - PREMIUM ONLY"""
    try:
        logger.info(f"Loading document {request.document_id} for user {user['email']}")

        # Initialize chat service
        chat_service = DocumentChatService(api_key)

        # Load and prepare document
        result = await chat_service.load_document(
            db=db,
            job_number=request.job_number,
            document_id=request.document_id,
            user_id=user["id"],
        )

        return DocumentLoadResponse(**result)

    except Exception as e:
        logger.error(f"Failed to load document: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to load document: {str(e)}"
        )


@router.post("/chat", response_model=DocumentChatResponse)
async def chat_with_document(
    request: DocumentChatRequest,
    user: dict = Depends(verify_premium_subscription),
    db: Session = Depends(get_db),
    api_key: str = Depends(get_api_key),
):
    """Chat with a specific document using AI - PREMIUM ONLY"""
    try:
        logger.info(
            f"Processing chat for document {request.document_id}, user {user['email']}"
        )

        # Initialize chat service
        chat_service = DocumentChatService(api_key)

        # Process the chat message
        result = await chat_service.process_chat_message(
            db=db,
            job_number=request.job_number,
            document_id=request.document_id,
            user_message=request.message,
            chat_history=request.chat_history,
            user_id=user["id"],
        )

        return DocumentChatResponse(**result)

    except Exception as e:
        logger.error(f"Chat processing failed: {e}")
        raise HTTPException(status_code=500, detail=f"Chat processing failed: {str(e)}")


@router.get("/chat-history/{job_number}/{document_id}")
async def get_chat_history(
    job_number: str,
    document_id: str,
    user: dict = Depends(verify_premium_subscription),
    db: Session = Depends(get_db),
    api_key: str = Depends(get_api_key),
):
    """Get chat history for a specific document"""
    try:
        chat_service = DocumentChatService(api_key)

        history = await chat_service.get_chat_history(
            db=db, job_number=job_number, document_id=document_id, user_id=user["id"]
        )

        return {
            "success": True,
            "chat_history": history,
            "document_id": document_id,
            "job_number": job_number,
        }

    except Exception as e:
        logger.error(f"Failed to get chat history: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to get chat history: {str(e)}"
        )


@router.post("/chat-history")
async def get_chat_history_post(
    request: DocumentChatHistoryRequest,
    user: dict = Depends(verify_premium_subscription),
    db: Session = Depends(get_db),
    api_key: str = Depends(get_api_key),
):
    """Get chat history for a specific document with configurable time window (POST method to avoid URL encoding issues)"""
    try:
        chat_service = DocumentChatService(api_key)

        # Validate hours_back parameter
        hours_back = max(
            1, min(request.hours_back or 24, 168)
        )  # Between 1 hour and 1 week

        history = await chat_service.get_chat_history(
            db=db,
            job_number=request.job_number,
            document_id=request.document_id,
            user_id=user["id"],
            hours_back=hours_back,
        )

        return {
            "success": True,
            "chat_history": history,
            "document_id": request.document_id,
            "job_number": request.job_number,
            "time_window_hours": hours_back,
            "message_count": len(history),
            "oldest_message_age_hours": (
                max((msg.get("session_age_hours", 0) for msg in history), default=0)
                if history
                else 0
            ),
        }

    except Exception as e:
        logger.error(f"Failed to get chat history: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to get chat history: {str(e)}"
        )


@router.post("/suggest-questions")
async def suggest_questions(
    request: DocumentLoadRequest,
    user: dict = Depends(verify_premium_subscription),
    db: Session = Depends(get_db),
    api_key: str = Depends(get_api_key),
):
    """Get AI-suggested questions for a document"""
    try:
        chat_service = DocumentChatService(api_key)

        suggestions = await chat_service.generate_suggested_questions(
            db=db,
            job_number=request.job_number,
            document_id=request.document_id,
            user_id=user["id"],
        )

        return {
            "success": True,
            "suggested_questions": suggestions,
            "document_id": request.document_id,
        }

    except Exception as e:
        logger.error(f"Failed to generate suggestions: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to generate suggestions: {str(e)}"
        )
