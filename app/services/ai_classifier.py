import requests
import time
import logging
from typing import Dict, Any, Optional
from datetime import datetime

from app.config import settings
from app.core.exceptions import AIClassificationError

logger = logging.getLogger("app.services.ai_classifier")


class AIClassifier:
   """Service for classifying documents using Claude AI"""
   
   def __init__(self, api_key: str):
       self.api_key = api_key
       self.base_url = "https://api.anthropic.com/v1/messages"
       self.headers = {
           "x-api-key": self.api_key,
           "Content-Type": "application/json",
           "anthropic-version": "2023-06-01",
       }
       self.logger = logger
   
   def _make_api_request(
       self, 
       prompt: str, 
       max_tokens: int = None, 
       max_retries: int = None
   ) -> str:
       """
       Make a request to Claude API with retry logic
       
       Args:
           prompt: The prompt to send to Claude
           max_tokens: Maximum tokens for response
           max_retries: Maximum number of retries
           
       Returns:
           Claude's response text
           
       Raises:
           AIClassificationError: If the API request fails
       """
       max_tokens = max_tokens or settings.anthropic_max_tokens
       max_retries = max_retries or settings.anthropic_max_retries
       
       data = {
           "model": settings.anthropic_model,
           "max_tokens": max_tokens,
           "messages": [{"role": "user", "content": prompt}],
       }
       
       for attempt in range(max_retries + 1):
           try:
               self.logger.debug(f"Making API request (attempt {attempt + 1})")
               
               response = requests.post(
                   self.base_url, 
                   headers=self.headers, 
                   json=data, 
                   timeout=settings.anthropic_timeout
               )
               
               if response.status_code == 200:
                   result = response.json()
                   return result["content"][0]["text"].strip()
               
               elif response.status_code == 529:
                   # API overloaded
                   if attempt < max_retries:
                       wait_time = (2**attempt) * 5  # Exponential backoff
                       self.logger.warning(
                           f"Claude API overloaded (529). Retrying in {wait_time}s... "
                           f"(attempt {attempt + 1}/{max_retries + 1})"
                       )
                       time.sleep(wait_time)
                       continue
                   else:
                       raise AIClassificationError(
                           "Claude API overloaded after multiple attempts",
                           details={"status_code": 529, "attempts": max_retries + 1}
                       )
               
               elif response.status_code == 429:
                   # Rate limited
                   if attempt < max_retries:
                       wait_time = 30 + (attempt * 10)  # 30s, 40s, 50s
                       self.logger.warning(
                           f"Claude API rate limited (429). Waiting {wait_time}s... "
                           f"(attempt {attempt + 1}/{max_retries + 1})"
                       )
                       time.sleep(wait_time)
                       continue
                   else:
                       raise AIClassificationError(
                           "Claude API rate limited after multiple attempts",
                           details={"status_code": 429, "attempts": max_retries + 1}
                       )
               
               else:
                   # Other HTTP error
                   error_detail = f"HTTP {response.status_code}"
                   try:
                       error_data = response.json()
                       error_detail += f": {error_data.get('error', {}).get('message', response.text)}"
                   except:
                       error_detail += f": {response.text}"
                   
                   raise AIClassificationError(
                       f"Claude API error: {error_detail}",
                       details={
                           "status_code": response.status_code,
                           "response": response.text[:500]  # Limit response text
                       }
                   )
           
           except requests.exceptions.Timeout:
               if attempt < max_retries:
                   self.logger.warning(f"Request timeout. Retrying... (attempt {attempt + 1})")
                   time.sleep(5)
                   continue
               else:
                   raise AIClassificationError(
                       "Request timeout after multiple attempts",
                       details={"timeout_seconds": settings.anthropic_timeout}
                   )
           
           except requests.exceptions.RequestException as e:
               if attempt < max_retries:
                   self.logger.warning(f"Request error: {e}. Retrying... (attempt {attempt + 1})")
                   time.sleep(5)
                   continue
               else:
                   raise AIClassificationError(
                       f"Request failed after multiple attempts: {str(e)}",
                       details={"error_type": type(e).__name__}
                   )
       
       raise AIClassificationError("Unexpected error in retry loop")
   
   def classify_document(
       self, 
       document_text: str, 
       filename: str, 
       job_name: str = ""
   ) -> Dict[str, Any]:
       """
       Classify a construction document
       
       Args:
           document_text: Text content of the document
           filename: Name of the file
           job_name: Name of the construction job
           
       Returns:
           Classification results dictionary
       """
       try:
           # Use a sample of the text for faster processing
           text_sample = document_text[:settings.max_text_sample_length]
           
           prompt = f"""
Analyze this CONSTRUCTION contract document and classify it.

FILENAME: {filename}
JOB: {job_name}

DOCUMENT SAMPLE:
{text_sample}

Respond in this EXACT format:

DOCUMENT_TYPE: [PRIMARY_CONTRACT, CHANGE_ORDER, LETTER_OF_INTENT, INSURANCE_DOCUMENT, SCHEDULE, AMENDMENT, PROPOSAL, INVOICE, CORRESPONDENCE, UNKNOWN]
IMPORTANCE: [CRITICAL, HIGH, MEDIUM, LOW]
STATUS: [EXECUTED_SIGNED, DRAFT_UNSIGNED, PROPOSAL, EXPIRED, UNKNOWN]
KEY_PARTIES: [Main companies mentioned]
DOLLAR_AMOUNT: [Any amounts, or NONE]
PROJECT_INFO: [Brief project description]
CONFIDENCE: [HIGH, MEDIUM, LOW]
SUMMARY: [One sentence description]
RECOMMENDATION: [ANALYZE_FULLY, REVIEW_MANUALLY, ARCHIVE, SKIP]
"""
           
           self.logger.debug(f"Classifying document: {filename}")
           response = self._make_api_request(prompt)
           
           classification = self._parse_classification_response(response, filename)
           
           # Add metadata
           classification.update({
               "classification_date": datetime.utcnow().isoformat(),
               "text_length": len(document_text),
               "ai_model": settings.anthropic_model
           })
           
           self.logger.info(f"Successfully classified {filename} as {classification.get('document_type')}")
           return classification
           
       except Exception as e:
           self.logger.error(f"Classification failed for {filename}: {e}")
           
           # Return error classification
           return {
               "filename": filename,
               "error": str(e),
               "document_type": "ERROR",
               "importance": "MEDIUM",
               "status": "UNKNOWN",
               "confidence": "LOW",
               "summary": f"Classification failed: {str(e)}",
               "recommendation": "REVIEW_MANUALLY",
               "classification_date": datetime.utcnow().isoformat(),
               "text_length": len(document_text),
               "ai_model": settings.anthropic_model
           }
   
   def _parse_classification_response(self, response: str, filename: str) -> Dict[str, Any]:
       """Parse Claude's structured response into a dictionary"""
       
       result = {
           "filename": filename,
           "document_type": "UNKNOWN",
           "importance": "MEDIUM",
           "status": "UNKNOWN",
           "key_parties": "",
           "dollar_amount": "NONE",
           "project_info": "",
           "confidence": "MEDIUM",
           "summary": "",
           "recommendation": "REVIEW_MANUALLY",
       }
       
       for line in response.split("\n"):
           if ":" not in line:
               continue
           
           key, value = line.split(":", 1)
           key = key.strip().upper()
           value = value.strip()
           
           if "DOCUMENT_TYPE" in key:
               result["document_type"] = value
           elif "IMPORTANCE" in key:
               result["importance"] = value
           elif "STATUS" in key:
               result["status"] = value
           elif "KEY_PARTIES" in key:
               result["key_parties"] = value
           elif "DOLLAR_AMOUNT" in key:
               result["dollar_amount"] = value
           elif "PROJECT_INFO" in key:
               result["project_info"] = value
           elif "CONFIDENCE" in key:
               result["confidence"] = value
           elif "SUMMARY" in key:
               result["summary"] = value
           elif "RECOMMENDATION" in key:
               result["recommendation"] = value
       
       return result


def create_ai_classifier(api_key: str) -> AIClassifier:
   """Factory function to create an AI classifier instance"""
   return AIClassifier(api_key)
