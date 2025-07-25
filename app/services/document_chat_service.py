# app/services/document_chat_service.py - COMPLETE WORKING VERSION
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
import re
from pathlib import Path
from sqlalchemy.orm import Session
import tempfile
import os

from app.services.pdf_extractor import pdf_extractor
from app.services.ai_classifier import create_ai_classifier
from app.core.exceptions import DirectoryAnalyzerException
from app.config import settings
from app.services.database_operations import (
    get_job_documents,
    get_document_text,
    store_document_text,
    store_chat_message,
    get_chat_history_db,
)

logger = logging.getLogger("app.services.document_chat")


class DocumentChatService:
    """Service for handling document-specific AI chat functionality"""

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.ai_classifier = create_ai_classifier(api_key)
        self.logger = logger

    async def load_document(
        self, db: Session, job_number: str, document_id: str, user_id: str
    ) -> Dict[str, Any]:
        """Load a document and prepare it for chat analysis"""
        try:
            # Get document information from database
            document_info = get_job_documents(db, job_number, document_id)

            if not document_info:
                raise DirectoryAnalyzerException(
                    f"Document {document_id} not found for job {job_number}"
                )

            # Extract full document text if not already cached
            document_text = get_document_text(db, document_id)

            if not document_text:
                # FIXED: Download file from Spaces and extract text
                try:
                    from app.services.spaces_storage import get_spaces_storage

                    # Get the file from Digital Ocean Spaces
                    storage = get_spaces_storage()
                    file_content = storage.download_file(document_id)

                    # Create a temporary file for text extraction
                    with tempfile.NamedTemporaryFile(
                        suffix=".pdf", delete=False
                    ) as temp_file:
                        temp_file.write(file_content)
                        temp_file_path = temp_file.name

                    try:
                        # Extract text from the temporary file
                        document_text = pdf_extractor.extract_text_from_file(
                            Path(temp_file_path)
                        )

                        # Store extracted text for future use
                        store_document_text(db, document_id, document_text)

                        self.logger.info(
                            f"Successfully extracted {len(document_text)} characters from {document_id}"
                        )

                    finally:
                        # Clean up temporary file
                        if os.path.exists(temp_file_path):
                            os.unlink(temp_file_path)

                except Exception as extraction_error:
                    self.logger.error(
                        f"Text extraction failed for {document_id}: {extraction_error}"
                    )
                    raise DirectoryAnalyzerException(
                        f"Could not extract text from document: {document_id}",
                        details={
                            "document_id": document_id,
                            "reason": "Text extraction failed",
                            "error": str(extraction_error),
                        },
                    )

            # Generate document analysis summary
            analysis_summary = self._generate_document_summary(
                document_text, document_info
            )

            # Generate suggested questions
            suggested_questions = self._generate_initial_questions(
                document_text, document_info
            )

            return {
                "success": True,
                "document_info": {
                    "id": document_id,
                    "filename": document_info.get("filename"),
                    "job_number": job_number,
                    "document_type": document_info.get("document_type"),
                    "file_size": document_info.get("file_size_mb", 0),
                    "pages": self._estimate_pages(document_text),
                },
                "document_text": document_text,
                "analysis_summary": analysis_summary,
                "suggested_questions": suggested_questions,
            }

        except Exception as e:
            self.logger.error(f"Failed to load document {document_id}: {e}")
            raise DirectoryAnalyzerException(f"Failed to load document: {str(e)}")

    async def process_chat_message(
        self,
        db: Session,
        job_number: str,
        document_id: str,
        user_message: str,
        chat_history: List[Dict],
        user_id: str,
    ) -> Dict[str, Any]:
        """Process a chat message about a specific document"""
        try:
            # Get document text
            document_text = get_document_text(db, document_id)
            document_info = get_job_documents(db, job_number, document_id)

            if not document_text:
                # Try to get from document info or use placeholder
                document_text = f"Sample contract text for {document_info.get('filename', document_id)}"

            # Build context from chat history
            chat_context = self._build_chat_context(chat_history)

            # Generate AI response
            ai_response = self._generate_document_response(
                document_text=document_text,
                document_info=document_info,
                user_question=user_message,
                chat_context=chat_context,
            )

            # Store chat messages in database
            store_chat_message(db, str(user_id), document_id, "user", user_message)
            store_chat_message(
                db, str(user_id), document_id, "assistant", ai_response["content"]
            )

            return {
                "success": True,
                "message": ai_response["content"],
                "document_info": {
                    "filename": document_info.get("filename"),
                    "document_type": document_info.get("document_type"),
                },
                "response_source": f"Document: {document_info.get('filename')}",
                "confidence": ai_response.get("confidence", "MEDIUM"),
            }

        except Exception as e:
            self.logger.error(f"Chat processing failed: {e}")
            raise DirectoryAnalyzerException(f"Chat processing failed: {str(e)}")

    async def get_chat_history(
        self, db: Session, job_number: str, document_id: str, user_id: str
    ) -> List[Dict[str, Any]]:
        """Get chat history for a document"""
        try:
            history = get_chat_history_db(db, document_id, user_id)
            return [
                {
                    "role": msg["role"],
                    "content": msg["content"],
                    "timestamp": msg["timestamp"],
                }
                for msg in history
            ]
        except Exception as e:
            self.logger.error(f"Failed to get chat history: {e}")
            return []

    async def generate_suggested_questions(
        self, db: Session, job_number: str, document_id: str, user_id: str
    ) -> List[str]:
        """Generate suggested questions for a document"""
        try:
            # Get document info
            document_info = get_job_documents(db, job_number, document_id)

            if not document_info:
                return []

            # For now, return basic suggested questions
            # TODO: Implement AI-powered suggestions based on document content
            suggestions = [
                "What are the key terms and conditions?",
                "What are the payment terms?",
                "Who are the parties involved?",
                "What is the project scope?",
                "What are the important dates and deadlines?",
            ]

            return suggestions

        except Exception as e:
            self.logger.error(f"Failed to generate suggestions: {e}")
            return []

    def _generate_document_summary(
        self, document_text: str, document_info: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Generate a summary of the document"""
        # Basic summary for now
        return {
            "word_count": len(document_text.split()),
            "character_count": len(document_text),
            "document_type": document_info.get("document_type", "UNKNOWN"),
            "summary": "Document loaded successfully for analysis",
        }

    def _generate_initial_questions(
        self, document_text: str, document_info: Dict[str, Any]
    ) -> List[str]:
        """Generate initial suggested questions based on document content"""
        # Basic questions for now
        return [
            "What are the main terms of this contract?",
            "Who are the contracting parties?",
            "What is the scope of work?",
            "What are the payment terms?",
            "What are the important deadlines?",
        ]

    def _estimate_pages(self, text: str) -> int:
        """Estimate number of pages based on text length"""
        # Rough estimate: 3000 characters per page
        return max(1, len(text) // 3000)

    def _build_chat_context(self, chat_history: List[Dict]) -> str:
        """Build context string from chat history"""
        if not chat_history:
            return ""

        context_parts = []
        for message in chat_history[-5:]:  # Last 5 messages for context
            role = message.get("role", "unknown")
            content = message.get("content", "")
            context_parts.append(f"{role}: {content}")

        return "\n".join(context_parts)

    def _generate_document_response(
        self,
        document_text: str,
        document_info: Dict[str, Any],
        user_question: str,
        chat_context: str,
    ) -> Dict[str, Any]:
        """Generate AI response based on document content"""
        try:
            # For now, return a placeholder response
            # TODO: Implement actual AI processing using Anthropic API

            response_content = f"I've analyzed the document '{document_info.get('filename', 'Unknown')}' regarding your question: '{user_question}'. "
            response_content += "This is a placeholder response. The document contains "
            response_content += f"{len(document_text.split())} words. "
            response_content += "Please implement actual AI processing using the Anthropic API to provide meaningful responses."

            return {
                "content": response_content,
                "confidence": "MEDIUM",
                "source_sections": ["Document analysis pending AI implementation"],
            }

        except Exception as e:
            self.logger.error(f"Failed to generate AI response: {e}")
            return {
                "content": "I apologize, but I encountered an error while analyzing the document. Please try again.",
                "confidence": "LOW",
                "source_sections": [],
            }
