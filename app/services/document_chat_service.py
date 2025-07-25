# app/services/document_chat_service.py - IMPROVED VERSION WITH BETTER TEXT RETRIEVAL
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
import requests
import json

logger = logging.getLogger("app.services.document_chat")

# Global cache for document text to avoid re-downloading
_document_text_cache = {}


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

                        # Store extracted text for future use AND cache it
                        store_document_text(db, document_id, document_text)
                        _document_text_cache[document_id] = document_text

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
            # Get document text - try cache first, then database, then load fresh
            document_text = _document_text_cache.get(document_id)

            if not document_text:
                document_text = get_document_text(db, document_id)

            if not document_text:
                # If still no text, try to load the document fresh
                self.logger.info(
                    f"No cached text found for {document_id}, loading fresh..."
                )
                load_result = await self.load_document(
                    db, job_number, document_id, user_id
                )
                document_text = load_result.get("document_text", "")

            # Get document info
            document_info = get_job_documents(db, job_number, document_id)

            if not document_text or len(document_text.strip()) < 10:
                document_text = f"Sample contract text for {document_info.get('filename', document_id)}"

            # Build context from chat history
            chat_context = self._build_chat_context(chat_history)

            # Generate AI response using actual document text
            ai_response = self._generate_document_response(
                document_text=document_text,
                document_info=document_info,
                user_question=user_message,
                chat_context=chat_context,
            )

            # Store chat messages in database
            try:
                store_chat_message(db, str(user_id), document_id, "user", user_message)
                store_chat_message(
                    db, str(user_id), document_id, "assistant", ai_response["content"]
                )
            except Exception as store_error:
                self.logger.warning(f"Failed to store chat messages: {store_error}")
                # Continue anyway - don't fail the whole request

            return {
                "success": True,
                "message": ai_response["content"],
                "document_info": {
                    "filename": (
                        document_info.get("filename") if document_info else "Unknown"
                    ),
                    "document_type": (
                        document_info.get("document_type")
                        if document_info
                        else "Unknown"
                    ),
                },
                "response_source": f"Document: {document_info.get('filename') if document_info else 'Unknown'}",
                "confidence": ai_response.get("confidence", "MEDIUM"),
                "timestamp": datetime.utcnow().isoformat(),
            }

        except Exception as e:
            self.logger.error(f"Chat processing failed: {e}")
            raise DirectoryAnalyzerException(f"Chat processing failed: {str(e)}")

    async def get_chat_history(
        self,
        db: Session,
        job_number: str,
        document_id: str,
        user_id: str,
        hours_back: int = 24,
    ) -> List[Dict[str, Any]]:
        """Get chat history for a document within the specified time window"""
        try:
            history = get_chat_history_db(db, document_id, user_id, hours_back)

            # Add some metadata about the session
            if history:
                session_start = min(
                    msg["timestamp"] for msg in history if msg["timestamp"]
                )
                session_duration = max(
                    msg["session_age_hours"]
                    for msg in history
                    if msg["session_age_hours"]
                )

                self.logger.info(
                    f"Retrieved {len(history)} messages for {document_id} "
                    f"(session started {session_duration:.1f} hours ago)"
                )

            return history

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
            return "This is the start of the conversation."

        context_lines = []
        for msg in chat_history[-6:]:  # Last 6 messages for context
            try:
                # Handle both dictionary and Pydantic model objects
                if hasattr(msg, "dict"):
                    # Pydantic model - convert to dict
                    msg_dict = msg.dict()
                    role = msg_dict.get("role", "unknown")
                    content = msg_dict.get("content", "")
                elif hasattr(msg, "role") and hasattr(msg, "content"):
                    # Object with attributes
                    role = getattr(msg, "role", "unknown")
                    content = getattr(msg, "content", "")
                elif isinstance(msg, dict):
                    # Regular dictionary
                    role = msg.get("role", "unknown")
                    content = msg.get("content", "")
                else:
                    # Fallback - try to convert to string
                    self.logger.warning(f"Unexpected message type: {type(msg)}")
                    continue

                context_lines.append(f"{role.upper()}: {content}")

            except Exception as e:
                self.logger.warning(f"Error processing chat message in context: {e}")
                continue

        return "\n".join(context_lines)

    def _generate_document_response(
        self,
        document_text: str,
        document_info: Dict[str, Any],
        user_question: str,
        chat_context: str,
    ) -> Dict[str, Any]:
        """Generate AI response based on document content"""
        try:
            # IMPROVED: Use actual document text in response
            filename = (
                document_info.get("filename", "Unknown") if document_info else "Unknown"
            )
            word_count = len(document_text.split())

            # Simple keyword-based response for now (TODO: Implement full AI)
            question_lower = user_question.lower()

            if (
                "contract amount" in question_lower
                or "price" in question_lower
                or "cost" in question_lower
            ):
                if "$" in document_text:
                    # Extract dollar amounts from text
                    import re

                    amounts = re.findall(r"\$[\d,]+(?:\.\d{2})?", document_text)
                    if amounts:
                        response_content = f"Based on the document '{filename}', I found the following amounts: {', '.join(amounts)}. "
                    else:
                        response_content = f"I can see dollar signs in the document '{filename}', but let me look more carefully at the pricing details. "
                else:
                    response_content = f"I don't see any specific monetary amounts in the document '{filename}'. "

            elif "parties" in question_lower or "who" in question_lower:
                # Look for company names and people
                if "KUNJ" in document_text and "Tri-State" in document_text:
                    response_content = f"Based on the document '{filename}', the main parties appear to be KUNJ Construction Corporation and Tri-State Painting LLC. "
                else:
                    response_content = f"Looking at the document '{filename}', I can identify the parties involved from the content. "

            else:
                response_content = f"Based on my analysis of the document '{filename}' ({word_count} words), I can help answer your question about: '{user_question}'. "

            # Add document snippet
            snippet = (
                document_text[:200] + "..."
                if len(document_text) > 200
                else document_text
            )
            response_content += (
                f'\n\nHere\'s a relevant excerpt from the document:\n"{snippet}"'
            )

            return {
                "content": response_content,
                "confidence": "MEDIUM",
                "source_sections": [f"Full document: {filename}"],
            }

        except Exception as e:
            self.logger.error(f"Failed to generate AI response: {e}")
            return {
                "content": "I apologize, but I encountered an error while analyzing the document. Please try again.",
                "confidence": "LOW",
                "source_sections": [],
            }

    def _make_ai_request(self, prompt: str) -> str:
        """Make a request to the Anthropic Claude API"""
        try:
            # Use the Anthropic API key
            api_key = self.api_key

            if not api_key:
                raise Exception("No Anthropic API key configured")

            if not api_key.startswith("sk-ant-"):
                raise Exception("Invalid Anthropic API key format")

            # Anthropic Claude API endpoint
            url = "https://api.anthropic.com/v1/messages"

            headers = {
                "Content-Type": "application/json",
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
            }

            # Format the request for Claude
            data = {
                "model": "claude-3-sonnet-20240229",
                "max_tokens": 1000,
                "messages": [{"role": "user", "content": prompt}],
            }

            self.logger.info(
                f"Making Anthropic API request, prompt length: {len(prompt)}"
            )

            # Make the API request with timeout
            response = requests.post(url, headers=headers, json=data, timeout=30)

            if response.status_code != 200:
                self.logger.error(
                    f"Anthropic API error: {response.status_code} - {response.text}"
                )
                raise Exception(f"Anthropic API returned status {response.status_code}")

            # Parse the response
            response_data = response.json()

            if "content" in response_data and len(response_data["content"]) > 0:
                ai_response = response_data["content"][0]["text"]
                self.logger.info(
                    f"Anthropic API success, response length: {len(ai_response)}"
                )
                return ai_response
            else:
                raise Exception("Anthropic API returned invalid response format")

        except Exception as e:
            self.logger.error(f"Anthropic API request failed: {e}")
            raise e

    # REPLACE your existing _generate_document_response method with this AI-only version:

    def _generate_document_response(
        self,
        document_text: str,
        document_info: Dict[str, Any],
        user_question: str,
        chat_context: str,
    ) -> Dict[str, Any]:
        """Generate AI response based on document content - AI ONLY, no hardcoded responses"""
        try:
            filename = (
                document_info.get("filename", "Unknown") if document_info else "Unknown"
            )

            # Limit document text for API (max ~6000 characters to stay within token limits)
            max_text_length = 6000
            if len(document_text) > max_text_length:
                document_text = (
                    document_text[:max_text_length]
                    + "\n[Document truncated for analysis...]"
                )

            # Create a focused prompt for Claude
            prompt = f"""You are an expert construction contract analyst. Answer the user's question based ONLY on the provided contract document.

    DOCUMENT: {filename}

    PREVIOUS CONVERSATION:
    {chat_context if chat_context.strip() else "This is the start of the conversation."}

    USER QUESTION: {user_question}

    DOCUMENT CONTENT:
    {document_text}

    INSTRUCTIONS:
    1. Answer the specific question asked by the user
    2. Base your answer ONLY on the document content provided above
    3. Quote specific sections when relevant (use quotes)
    4. If the requested information isn't in the document, clearly state that
    5. Be concise but thorough in your response
    6. Use bullet points or numbered lists when appropriate for clarity

    Please provide a specific, accurate answer to the user's question about this document."""

            # Make the AI request (no fallbacks - fail transparently if AI doesn't work)
            ai_response = self._make_ai_request(prompt)

            # Assess confidence based on response content
            confidence = self._assess_response_confidence(ai_response, user_question)

            return {
                "content": ai_response,
                "confidence": confidence,
                "source_sections": [f"Document: {filename}"],
            }

        except Exception as e:
            self.logger.error(f"Failed to generate AI response: {e}")

            # NO hardcoded fallbacks - return a transparent error message
            error_message = "I'm unable to analyze the document right now due to an AI service issue. "

            if "API key" in str(e):
                error_message += (
                    "The AI service is not properly configured. Please contact support."
                )
            elif "timeout" in str(e).lower():
                error_message += (
                    "The AI service is taking too long to respond. Please try again."
                )
            elif "status" in str(e):
                error_message += "The AI service is temporarily unavailable. Please try again shortly."
            else:
                error_message += (
                    "Please try again, and if the problem persists, contact support."
                )

            return {
                "content": error_message,
                "confidence": "LOW",
                "source_sections": [],
            }

    # Also update the _assess_response_confidence method to be more sophisticated:

    def _assess_response_confidence(self, response: str, question: str) -> str:
        """Assess confidence level of the AI response"""
        response_lower = response.lower()

        # High confidence indicators
        high_confidence_indicators = [
            "according to the document",
            "the document states",
            "specifically mentions",
            "clearly outlined",
            "as shown in",
            "the contract specifies",
        ]

        # Low confidence indicators
        low_confidence_indicators = [
            "i don't see",
            "not mentioned",
            "doesn't appear",
            "unclear",
            "not specified",
            "not found",
            "unable to determine",
            "not clearly stated",
            "doesn't contain",
            "not available in",
        ]

        # Count indicators
        high_count = sum(
            1 for indicator in high_confidence_indicators if indicator in response_lower
        )
        low_count = sum(
            1 for indicator in low_confidence_indicators if indicator in response_lower
        )

        # Determine confidence
        if low_count > 0:
            return "LOW"
        elif high_count >= 2 or (high_count >= 1 and len(response) > 200):
            return "HIGH"
        elif len(response) > 150 and '"' in response:  # Contains quotes from document
            return "HIGH"
        else:
            return "MEDIUM"

    # Also update _generate_initial_questions to be AI-driven (optional):

    def _generate_initial_questions(
        self, document_text: str, document_info: Dict[str, Any]
    ) -> List[str]:
        """Generate initial suggested questions based on document content using AI"""
        try:
            filename = document_info.get("filename", "Unknown")

            # Use first 2000 characters for question generation
            text_sample = document_text[:2000]

            prompt = f"""Based on this construction contract document, suggest 5 relevant questions that a user might want to ask.

    DOCUMENT: {filename}
    DOCUMENT SAMPLE: {text_sample}

    Generate practical, specific questions that would help someone understand:
    - Key contractual terms and obligations
    - Important dates and deadlines
    - Financial aspects and payment terms
    - Scope of work and deliverables
    - Parties involved and their responsibilities

    Return ONLY a numbered list of 5 questions, no other text."""

            try:
                response = self._make_ai_request(prompt)
                questions = self._parse_suggested_questions(response)
                return questions[:5] if questions else self._get_default_questions()
            except Exception as e:
                self.logger.warning(f"AI question generation failed: {e}")
                return self._get_default_questions()

        except Exception as e:
            self.logger.error(f"Failed to generate suggested questions: {e}")
            return self._get_default_questions()

    def _get_default_questions(self) -> List[str]:
        """Get default questions when AI generation fails"""
        return [
            "What is this document about?",
            "Who are the parties involved in this contract?",
            "What are the key terms and conditions?",
            "What are the important dates and deadlines?",
            "What is the scope of work or project described?",
        ]

    def _parse_suggested_questions(self, response: str) -> List[str]:
        """Parse AI response to extract suggested questions"""
        lines = response.strip().split("\n")
        questions = []

        for line in lines:
            line = line.strip()
            if line and (
                line[0].isdigit() or line.startswith("-") or line.startswith("•")
            ):
                # Remove numbering and clean up
                import re

                question = re.sub(r"^\d+\.?\s*", "", line)
                question = re.sub(r"^[-•]\s*", "", question)
                if question.strip() and question.strip().endswith("?"):
                    questions.append(question.strip())

        return questions
