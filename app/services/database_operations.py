# app/services/database_operations.py
from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import and_, desc
import logging
from uuid import UUID

from app.models.database import User, Job, Contract, TextExtraction, ChatMessage
from app.core.database import get_db
from app.services.spaces_storage import get_spaces_storage

logger = logging.getLogger("app.services.database_operations")


def get_job_documents(db: Session, job_number: str, document_id: str) -> Optional[Dict]:
    """Get document info from Digital Ocean Spaces (since DB is empty)"""
    try:
        # If document_id is a full Spaces path, extract user_id and find the document
        if document_id.startswith("users/") and "/" in document_id:
            path_parts = document_id.split("/")
            user_id = path_parts[1]

            # Get contracts from Spaces
            storage = get_spaces_storage()
            contracts = storage.list_job_contracts(user_id, job_number)

            # Find the matching document
            for contract in contracts:
                if contract["file_key"] == document_id:
                    return {
                        "id": document_id,
                        "filename": contract.get(
                            "original_filename", document_id.split("/")[-1]
                        ),
                        "file_path": contract["file_key"],  # This is the Spaces path
                        "document_type": contract.get("contract_type", "UNKNOWN"),
                        "file_size_mb": contract.get("size", 0) / (1024 * 1024),
                        "job_number": job_number,
                        "public_url": contract.get("public_url"),
                    }

        logger.warning(f"Document {document_id} not found for job {job_number}")
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
