# app/services/database_operations.py - FIXED VERSION TO WORK WITH SPACES
from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import and_, desc, or_
import logging
from uuid import UUID

from app.models.database import User, Job, Contract, TextExtraction, ChatMessage
from app.core.database import get_db

logger = logging.getLogger("app.services.database_operations")


def get_job_documents(db: Session, job_number: str, document_id: str) -> Optional[Dict]:
    """Get document info from Digital Ocean Spaces (since DB is empty)"""
    try:
        # If document_id is a full Spaces path, extract user_id
        if document_id.startswith("users/") and "/" in document_id:
            path_parts = document_id.split("/")
            user_id = path_parts[1]

            # Get contracts from Spaces
            from app.services.spaces_storage import get_spaces_storage

            storage = get_spaces_storage()
            contracts = storage.list_job_contracts(user_id, job_number)

            # Find the matching document
            for contract in contracts:
                if contract["file_key"] == document_id:
                    # Extract filename from the full path
                    filename = contract.get("original_filename")
                    if not filename and "/" in document_id:
                        # Extract from the path if metadata is missing
                        filename = document_id.split("/")[-1]
                        # Remove timestamp prefix if present
                        import re

                        if re.match(r"^\d{8}_\d{6}_[a-f0-9]+_", filename):
                            filename = re.sub(r"^\d{8}_\d{6}_[a-f0-9]+_", "", filename)

                    return {
                        "id": document_id,
                        "filename": filename,
                        "file_path": contract["file_key"],  # This is the Spaces path
                        "document_type": contract.get("contract_type", "UNKNOWN"),
                        "file_size_mb": contract.get("size", 0) / (1024 * 1024),
                        "job_number": job_number,
                        "public_url": contract.get("public_url"),
                        "is_main_contract": contract.get("is_main_contract", False),
                        "upload_timestamp": contract.get("upload_timestamp"),
                    }

        # Fallback: try database lookup (in case some contracts are in DB)
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
                "job_number": job_number,
                "job_id": str(contract.job_id),
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
            # Try by file_key (for Spaces documents)
            contract = (
                db.query(Contract).filter(Contract.file_key == document_id).first()
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
        # Find contract by various methods
        contract = (
            db.query(Contract).filter(Contract.original_filename == document_id).first()
        )

        if not contract:
            # Try by file_key (for Spaces documents)
            contract = (
                db.query(Contract).filter(Contract.file_key == document_id).first()
            )

        if not contract:
            try:
                contract_uuid = UUID(document_id)
                contract = (
                    db.query(Contract).filter(Contract.id == contract_uuid).first()
                )
            except ValueError:
                logger.warning(
                    f"Could not find contract for document_id: {document_id}"
                )
                # For Spaces documents, we might not have a database record yet
                # In this case, we can't store the text in the database
                # But we can still cache it in memory (handled by the service)
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
            logger.info(f"Stored text extraction for document: {document_id}")

    except Exception as e:
        logger.error(f"Error storing document text: {e}")
        db.rollback()


def store_chat_message(
    db: Session, user_id: str, document_id: str, role: str, content: str
):
    """Store chat message using ChatMessage model"""
    try:
        # Find contract for context (try multiple methods)
        contract = None

        # Try by original filename
        contract = (
            db.query(Contract).filter(Contract.original_filename == document_id).first()
        )

        if not contract:
            # Try by file_key (for Spaces documents)
            contract = (
                db.query(Contract).filter(Contract.file_key == document_id).first()
            )

        if not contract:
            try:
                contract_uuid = UUID(document_id)
                contract = (
                    db.query(Contract).filter(Contract.id == contract_uuid).first()
                )
            except ValueError:
                pass

        # Create chat message (with or without contract_id)
        chat_message = ChatMessage(
            user_id=UUID(user_id),
            contract_id=contract.id if contract else None,
            role=role,
            content=content,
            document_filename=document_id,  # Store the document path for reference
            job_number=None,  # Could extract from document_id if needed
            confidence=None,
        )

        db.add(chat_message)
        db.commit()

        logger.info(f"Stored chat message for document: {document_id}")

    except Exception as e:
        logger.error(f"Error storing chat message: {e}")
        db.rollback()


def get_chat_history_db(
    db: Session, document_id: str, user_id: str
) -> List[Dict[str, Any]]:
    """Get chat history for a document"""
    try:
        # Find by document filename or contract ID
        messages = (
            db.query(ChatMessage)
            .filter(
                and_(
                    ChatMessage.user_id == UUID(user_id),
                    or_(
                        ChatMessage.document_filename == document_id,
                        ChatMessage.contract_id.in_(
                            db.query(Contract.id).filter(
                                or_(
                                    Contract.original_filename == document_id,
                                    Contract.file_key == document_id,
                                )
                            )
                        ),
                    ),
                )
            )
            .order_by(ChatMessage.created_at)
            .all()
        )

        return [
            {
                "role": msg.role,
                "content": msg.content,
                "timestamp": msg.created_at.isoformat() if msg.created_at else None,
            }
            for msg in messages
        ]

    except Exception as e:
        logger.error(f"Error getting chat history: {e}")
        return []
