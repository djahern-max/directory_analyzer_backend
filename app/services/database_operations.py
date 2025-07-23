# app/services/database_operations.py
from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import and_, desc
import logging
from uuid import UUID

from app.models.database import User, Job, Contract, TextExtraction, ChatMessage
from app.core.database import get_db

logger = logging.getLogger("app.services.database_operations")


def get_job_documents(db: Session, job_number: str, document_id: str) -> Optional[Dict]:
    """Get document info from database using existing models"""
    try:
        # Convert document_id to contract filename for lookup
        contract = (
            db.query(Contract)
            .join(Job)
            .filter(
                and_(
                    Job.job_number == job_number,
                    Contract.original_filename == document_id,
                )
            )
            .first()
        )

        if not contract:
            # Try by contract ID if it's a UUID
            try:
                contract_uuid = UUID(document_id)
                contract = (
                    db.query(Contract)
                    .join(Job)
                    .filter(
                        and_(Job.job_number == job_number, Contract.id == contract_uuid)
                    )
                    .first()
                )
            except ValueError:
                pass

        if contract:
            return {
                "id": str(contract.id),
                "filename": contract.original_filename,
                "file_path": contract.file_key,  # Storage key
                "document_type": (
                    contract.contract_type.value
                    if contract.contract_type
                    else "UNKNOWN"
                ),
                "file_size_mb": contract.file_size_bytes / (1024 * 1024),
                "job_id": str(contract.job_id),
            }

        return None

    except Exception as e:
        logger.error(f"Error getting job documents: {e}")
        return None


def get_document_text(db: Session, document_id: str) -> Optional[str]:
    """Get cached document text using existing TextExtraction model"""
    try:
        # Find by contract filename first
        contract = (
            db.query(Contract).filter(Contract.original_filename == document_id).first()
        )

        if not contract:
            # Try by UUID
            try:
                contract_uuid = UUID(document_id)
                contract = (
                    db.query(Contract).filter(Contract.id == contract_uuid).first()
                )
            except ValueError:
                return None

        if contract:
            text_extraction = (
                db.query(TextExtraction)
                .filter(TextExtraction.contract_id == contract.id)
                .first()
            )

            if text_extraction and text_extraction.extraction_success:
                return text_extraction.extracted_text

        return None

    except Exception as e:
        logger.error(f"Error getting document text: {e}")
        return None


def store_document_text(db: Session, document_id: str, text: str):
    """Store extracted document text using existing TextExtraction model"""
    try:
        # Find contract
        contract = (
            db.query(Contract).filter(Contract.original_filename == document_id).first()
        )

        if not contract:
            try:
                contract_uuid = UUID(document_id)
                contract = (
                    db.query(Contract).filter(Contract.id == contract_uuid).first()
                )
            except ValueError:
                logger.error(f"Could not find contract for document_id: {document_id}")
                return

        if contract:
            # Check if text extraction already exists
            existing = (
                db.query(TextExtraction)
                .filter(TextExtraction.contract_id == contract.id)
                .first()
            )

            if existing:
                # Update existing
                existing.extracted_text = text
                existing.text_length = len(text)
                existing.extraction_success = True
                existing.extraction_method = "pdf_extractor"
            else:
                # Create new
                text_extraction = TextExtraction(
                    contract_id=contract.id,
                    extraction_method="pdf_extractor",
                    extracted_text=text,
                    text_length=len(text),
                    extraction_success=True,
                )
                db.add(text_extraction)

            db.commit()

    except Exception as e:
        logger.error(f"Error storing document text: {e}")
        db.rollback()


def store_chat_message(
    db: Session, user_id: str, document_id: str, role: str, content: str
):
    """Store chat message using ChatMessage model"""
    try:
        # Find contract for context
        contract = (
            db.query(Contract).filter(Contract.original_filename == document_id).first()
        )

        if not contract:
            try:
                contract_uuid = UUID(document_id)
                contract = (
                    db.query(Contract).filter(Contract.id == contract_uuid).first()
                )
            except ValueError:
                pass

        # Create chat message
        chat_message = ChatMessage(
            user_id=UUID(user_id),
            contract_id=contract.id if contract else None,
            role=role,
            content=content,
            document_filename=contract.original_filename if contract else document_id,
            job_number=contract.job.job_number if contract and contract.job else None,
        )

        db.add(chat_message)
        db.commit()

    except Exception as e:
        logger.error(f"Error storing chat message: {e}")
        db.rollback()


def get_chat_history_db(db: Session, user_id: str, document_id: str) -> List[Dict]:
    """Get chat history using ChatMessage model"""
    try:
        # Find contract
        contract = (
            db.query(Contract).filter(Contract.original_filename == document_id).first()
        )

        if not contract:
            try:
                contract_uuid = UUID(document_id)
                contract = (
                    db.query(Contract).filter(Contract.id == contract_uuid).first()
                )
            except ValueError:
                return []

        if contract:
            messages = (
                db.query(ChatMessage)
                .filter(
                    and_(
                        ChatMessage.user_id == UUID(user_id),
                        ChatMessage.contract_id == contract.id,
                    )
                )
                .order_by(ChatMessage.created_at)
                .all()
            )

            return [
                {
                    "id": str(msg.id),
                    "role": msg.role,
                    "content": msg.content,
                    "timestamp": msg.created_at.isoformat(),
                    "confidence": msg.confidence,
                }
                for msg in messages
            ]

        return []

    except Exception as e:
        logger.error(f"Error getting chat history: {e}")
        return []
