# app/services/document_chat_service.py
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
import re
from pathlib import Path
from sqlalchemy.orm import Session

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
        self, db: Session, job_number: str, document_id: str, user_id: int
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
                # Extract text from file if file path exists
                file_path = Path(document_info.get("file_path", ""))
                if file_path.exists():
                    document_text = pdf_extractor.extract_text_from_file(file_path)
                    # Store extracted text for future use
                    store_document_text(db, document_id, document_text)
                else:
                    # For demo purposes, use placeholder text
                    raise DirectoryAnalyzerException(
                        f"Could not extract text from document: {document_id}",
                        details={
                            "document_id": document_id,
                            "reason": "Text extraction failed",
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
        user_id: int,
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
                "timestamp": datetime.utcnow(),
            }

        except Exception as e:
            self.logger.error(f"Failed to process chat message: {e}")
            raise DirectoryAnalyzerException(f"Chat processing failed: {str(e)}")

    async def get_chat_history(
        self, db: Session, job_number: str, document_id: str, user_id: int
    ) -> List[Dict]:
        """Retrieve chat history for a document"""
        try:
            return get_chat_history_db(db, str(user_id), document_id)
        except Exception as e:
            self.logger.error(f"Failed to get chat history: {e}")
            return []

    async def generate_suggested_questions(
        self, db: Session, job_number: str, document_id: str, user_id: int
    ) -> List[str]:
        """Generate AI-suggested questions for a document"""
        try:
            document_text = get_document_text(db, document_id)
            document_info = get_job_documents(db, job_number, document_id)

            if not document_text:
                document_text = (
                    f"Sample contract for {document_info.get('filename', document_id)}"
                )

            return self._generate_initial_questions(document_text, document_info)

        except Exception as e:
            self.logger.error(f"Failed to generate suggestions: {e}")
            return []

    def _generate_document_summary(
        self, document_text: str, document_info: Dict
    ) -> Dict[str, Any]:
        """Generate an AI summary of the document"""

        # Use first portion of text for summary
        text_sample = document_text[:5000]

        prompt = f"""
Analyze this construction contract document and provide a comprehensive summary.

DOCUMENT INFO:
- Filename: {document_info.get('filename', 'Unknown')}
- Type: {document_info.get('document_type', 'Unknown')}

DOCUMENT TEXT:
{text_sample}

Provide a summary in this format:

DOCUMENT_PURPOSE: [Brief description of what this document is for]
KEY_PARTIES: [Main companies/individuals involved]
PROJECT_SCOPE: [What work/project this covers]
IMPORTANT_DATES: [Key dates, deadlines, or timeframes]
FINANCIAL_TERMS: [Contract values, payment terms, or financial obligations]
CRITICAL_CLAUSES: [Important terms, conditions, or requirements]
RISK_FACTORS: [Potential issues or important considerations]
"""

        try:
            response = self._make_ai_request(prompt)
            return self._parse_document_summary(response)
        except Exception as e:
            self.logger.error(f"Failed to generate document summary: {e}")
            return {"error": "Could not generate summary"}

    def _generate_document_response(
        self,
        document_text: str,
        document_info: Dict,
        user_question: str,
        chat_context: str,
    ) -> Dict[str, Any]:
        """Generate an AI response to a user question about the document"""

        # Limit document text for context (keep within token limits)
        max_text_length = 8000
        if len(document_text) > max_text_length:
            document_text = (
                document_text[:max_text_length]
                + "\n[Document truncated for analysis...]"
            )

        prompt = f"""
You are an expert construction contract analyst. Answer the user's question based ONLY on the provided contract document.

DOCUMENT INFORMATION:
- Filename: {document_info.get('filename', 'Unknown')}
- Document Type: {document_info.get('document_type', 'Unknown')}

PREVIOUS CONVERSATION:
{chat_context}

DOCUMENT CONTENT:
{document_text}

USER QUESTION: {user_question}

INSTRUCTIONS:
1. Answer based ONLY on information found in this document
2. Be specific and cite relevant sections when possible
3. If the information isn't in the document, clearly state that
4. Provide practical, actionable insights when relevant
5. Format your response clearly with bullet points or sections when appropriate

RESPONSE:
"""

        try:
            response = self._make_ai_request(prompt)

            # Determine confidence based on response content
            confidence = self._assess_response_confidence(response, user_question)

            return {"content": response, "confidence": confidence}
        except Exception as e:
            self.logger.error(f"Failed to generate AI response: {e}")
            return {
                "content": "I apologize, but I'm having trouble analyzing this document right now. Please try again.",
                "confidence": "LOW",
            }

    def _generate_initial_questions(
        self, document_text: str, document_info: Dict
    ) -> List[str]:
        """Generate suggested questions based on document content"""

        text_sample = document_text[:3000]

        prompt = f"""
Based on this construction contract document, suggest 6 relevant questions that a user might want to ask.

DOCUMENT TYPE: {document_info.get('document_type', 'Unknown')}
FILENAME: {document_info.get('filename', 'Unknown')}

DOCUMENT SAMPLE:
{text_sample}

Generate practical questions that would help someone understand:
- Key terms and obligations
- Important dates and deadlines  
- Financial aspects
- Risk factors
- Scope of work
- Performance requirements

Return ONLY a numbered list of questions, no other text.
"""

        try:
            response = self._make_ai_request(prompt)
            questions = self._parse_suggested_questions(response)
            return questions[:6]  # Limit to 6 questions
        except Exception as e:
            self.logger.error(f"Failed to generate suggested questions: {e}")
            return [
                "What are the key terms and conditions in this contract?",
                "What are the important dates and deadlines?",
                "What are the payment terms and financial obligations?",
                "What is the scope of work covered?",
                "What are the main risks or potential issues?",
                "Who are the key parties and their responsibilities?",
            ]

    def _build_chat_context(self, chat_history: List[Dict]) -> str:
        """Build context string from chat history"""
        if not chat_history:
            return "This is the start of the conversation."

        context_lines = []
        for msg in chat_history[-6:]:  # Last 6 messages for context
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            context_lines.append(f"{role.upper()}: {content}")

        return "\n".join(context_lines)

    def _estimate_pages(self, document_text: str) -> int:
        """Estimate number of pages based on text length"""
        # Rough estimate: ~2500 characters per page
        return max(1, len(document_text) // 2500)

    def _assess_response_confidence(self, response: str, question: str) -> str:
        """Assess confidence level of the AI response"""

        # Check for uncertainty indicators
        uncertainty_phrases = [
            "i don't see",
            "not mentioned",
            "doesn't appear",
            "unclear",
            "not specified",
            "not found",
            "unable to determine",
        ]

        response_lower = response.lower()

        if any(phrase in response_lower for phrase in uncertainty_phrases):
            return "LOW"
        elif len(response) > 200 and "specifically" in response_lower:
            return "HIGH"
        else:
            return "MEDIUM"

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
                question = re.sub(r"^\d+\.?\s*", "", line)
                question = re.sub(r"^[-•]\s*", "", question)
                if question.strip():
                    questions.append(question.strip())

        return questions

    def _parse_document_summary(self, response: str) -> Dict[str, Any]:
        """Parse AI response to extract document summary components"""
        summary = {}

        patterns = {
            "purpose": r"DOCUMENT_PURPOSE:\s*(.+)",
            "parties": r"KEY_PARTIES:\s*(.+)",
            "scope": r"PROJECT_SCOPE:\s*(.+)",
            "dates": r"IMPORTANT_DATES:\s*(.+)",
            "financial": r"FINANCIAL_TERMS:\s*(.+)",
            "clauses": r"CRITICAL_CLAUSES:\s*(.+)",
            "risks": r"RISK_FACTORS:\s*(.+)",
        }

        for key, pattern in patterns.items():
            match = re.search(pattern, response, re.IGNORECASE | re.MULTILINE)
            if match:
                summary[key] = match.group(1).strip()
            else:
                summary[key] = "Not specified"

        return summary

    def _make_ai_request(self, prompt: str) -> str:
        """Make a request to the AI service"""
        try:
            # Use the existing AI classifier's request method
            return self.ai_classifier._make_api_request(prompt)
        except Exception as e:
            self.logger.error(f"AI request failed: {e}")
            raise
