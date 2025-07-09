import logging
from typing import List, Dict, Any, Optional
from pathlib import Path

from app.models.document import DocumentType, ImportanceLevel, DocumentStatus, PriorityLevel
from app.core.exceptions import DirectoryAnalyzerException

logger = logging.getLogger("app.services.document_analyzer")


class DocumentAnalyzer:
   """Service for analyzing and scoring documents"""
   
   def __init__(self):
       self.logger = logger
   
   def score_document_importance(self, classification: Dict[str, Any]) -> int:
       """
       Calculate importance score for a document based on various factors
       
       Args:
           classification: Document classification dictionary
           
       Returns:
           Numerical importance score (higher = more important)
       """
       score = 0
       
       # Base importance scoring
       importance_scores = {
           "CRITICAL": 100,
           "HIGH": 70,
           "MEDIUM": 40,
           "LOW": 20
       }
       
       importance = classification.get("importance", "MEDIUM")
       score += importance_scores.get(importance, 40)
       
       # Document type scoring
       type_scores = {
           "PRIMARY_CONTRACT": 50,
           "CHANGE_ORDER": 30,
           "AMENDMENT": 25,
           "LETTER_OF_INTENT": 20,
           "INSURANCE_DOCUMENT": 15,
           "SCHEDULE": 10,
           "CORRESPONDENCE": 10,
           "PROPOSAL": 5,
           "INVOICE": 5
       }
       
       doc_type = classification.get("document_type", "")
       score += type_scores.get(doc_type, 0)
       
       # Status bonus points
       status = classification.get("status", "")
       if status == "EXECUTED_SIGNED":
           score += 30
       elif status == "DRAFT_UNSIGNED":
           score += 10
       elif status == "PROPOSAL":
           score += 5
       
       # Filename analysis for contract indicators
       filename = classification.get("filename", "").lower()
       
       # Strong indicators of main/final contract
       main_indicators = ["executed", "signed", "final", "fully executed"]
       if any(indicator in filename for indicator in main_indicators):
           score += 25
       
       # Clean/final version indicators
       clean_indicators = ["clean", "final copy", "executed copy"]
       if any(indicator in filename for indicator in clean_indicators):
           score += 20
       
       # Version progression (higher revisions typically more important)
       version_patterns = [
           ("r3", 22), ("rev3", 22), ("revision 3", 22),
           ("r2", 18), ("rev2", 18), ("revision 2", 18),
           ("r1", 15), ("rev1", 15), ("revision 1", 15)
       ]
       
       for pattern, points in version_patterns:
           if pattern in filename:
               score += points
               break  # Only count one version pattern
       
       # Contract number/reference indicators
       contract_indicators = ["contract", "agreement", "ctdot"]
       if any(indicator in filename for indicator in contract_indicators):
           score += 10
       
       # Draft/markup indicators (reduce score)
       draft_indicators = ["markup", "mark up", "draft", "redline", "comments"]
       if any(indicator in filename for indicator in draft_indicators):
           score -= 10
       
       # File size considerations (larger files often more comprehensive)
       text_length = classification.get("text_length", 0)
       if text_length > 100000:  # >100k characters
           score += 15
       elif text_length > 50000:  # >50k characters
           score += 10
       elif text_length > 20000:  # >20k characters
           score += 5
       
       # Confidence bonus
       confidence = classification.get("confidence", "MEDIUM")
       if confidence == "HIGH":
           score += 5
       elif confidence == "LOW":
           score -= 5
       
       # Ensure minimum score
       return max(score, 0)
   
   def identify_main_contract(
       self, 
       classifications: List[Dict[str, Any]]
   ) -> Optional[Dict[str, Any]]:
       """
       Identify the main contract from a list of document classifications
       
       Args:
           classifications: List of document classification dictionaries
           
       Returns:
           Main contract classification with additional metadata, or None
       """
       if not classifications:
           self.logger.warning("No classifications provided for main contract identification")
           return None
       
       # Score all documents
       scored_docs = []
       for classification in classifications:
           if classification.get("error"):
               continue  # Skip error classifications
           
           score = self.score_document_importance(classification)
           scored_docs.append({
               "classification": classification,
               "score": score
           })
       
       if not scored_docs:
           self.logger.warning("No valid classifications for scoring")
           return None
       
       # Sort by score (highest first)
       scored_docs.sort(key=lambda x: x["score"], reverse=True)
       
       # Look for primary contracts first
       primary_contracts = [
           doc for doc in scored_docs
           if doc["classification"].get("document_type") == "PRIMARY_CONTRACT"
       ]
       
       main_contract = None
       ranking_reason = ""
       
       if primary_contracts:
           # Among primary contracts, look for definitive indicators
           for doc in primary_contracts:
               filename = doc["classification"].get("filename", "").lower()
               
               # Check for strong main contract indicators
               strong_indicators = ["executed", "clean", "final", "signed"]
               if any(indicator in filename for indicator in strong_indicators):
                   main_contract = doc
                   ranking_reason = f"Primary contract with '{next(ind for ind in strong_indicators if ind in filename)}' indicator"
                   break
           
           # If no clear indicators, use highest scoring primary contract
           if not main_contract:
               main_contract = primary_contracts[0]
               ranking_reason = f"Highest scoring among {len(primary_contracts)} primary contracts"
       
       else:
           # No primary contracts found, use highest scoring document overall
           main_contract = scored_docs[0]
           doc_type = main_contract["classification"].get("document_type", "UNKNOWN")
           ranking_reason = f"Highest scoring document (type: {doc_type}) - no primary contracts found"
       
       # Add main contract metadata
       main_contract["classification"]["is_main_contract"] = True
       main_contract["classification"]["importance_score"] = main_contract["score"]
       main_contract["classification"]["ranking_reason"] = ranking_reason
       main_contract["classification"]["total_documents_analyzed"] = len(classifications)
       
       self.logger.info(
           f"Identified main contract: {main_contract['classification']['filename']} "
           f"(score: {main_contract['score']}, reason: {ranking_reason})"
       )
       
       return main_contract["classification"]
   
   def rank_documents(
       self, 
       classifications: List[Dict[str, Any]]
   ) -> List[Dict[str, Any]]:
       """
       Rank all documents by importance with enhanced metadata
       
       Args:
           classifications: List of document classification dictionaries
           
       Returns:
           List of ranked documents with additional metadata
       """
       if not classifications:
           return []
       
       # First identify the main contract
       main_contract_data = self.identify_main_contract(classifications)
       main_filename = main_contract_data.get("filename") if main_contract_data else None
       
       # Score and enhance all documents
       scored_docs = []
       for classification in classifications:
           score = self.score_document_importance(classification)
           
           enhanced_classification = classification.copy()
           enhanced_classification["importance_score"] = score
           
           # Set main contract flag
           is_main = (main_filename and classification.get("filename") == main_filename)
           enhanced_classification["is_main_contract"] = is_main
           
           if is_main and main_contract_data:
               enhanced_classification["ranking_reason"] = main_contract_data.get("ranking_reason")
           
           scored_docs.append(enhanced_classification)
       
       # Sort by score (highest first)
       scored_docs.sort(key=lambda x: x["importance_score"], reverse=True)
       
       # Add rank numbers and priority levels
       for i, doc in enumerate(scored_docs, 1):
           doc["rank"] = i
           doc["priority_level"] = self._determine_priority_level(doc, i)
       
       self.logger.info(f"Ranked {len(scored_docs)} documents")
       return scored_docs
   
   def _determine_priority_level(self, doc: Dict[str, Any], rank: int) -> str:
       """Determine the priority level for a document"""
       
       if doc.get("is_main_contract"):
           return PriorityLevel.MAIN_CONTRACT.value
       
       elif doc.get("document_type") == "PRIMARY_CONTRACT" and rank <= 3:
           return PriorityLevel.HIGH_PRIORITY.value
       
       elif doc.get("recommendation") == "ANALYZE_FULLY":
           return PriorityLevel.ANALYZE_RECOMMENDED.value
       
       else:
           return PriorityLevel.SUPPORTING_DOCUMENT.value
   
   def generate_classification_summary(
       self, 
       classifications: List[Dict[str, Any]]
   ) -> Dict[str, Any]:
       """
       Generate a summary of document classifications
       
       Args:
           classifications: List of document classification dictionaries
           
       Returns:
           Summary statistics dictionary
       """
       if not classifications:
           return {
               "total_documents": 0,
               "by_type": {},
               "by_importance": {},
               "by_status": {},
               "recommendations": {}
           }
       
       # Count by various categories
       by_type = {}
       by_importance = {}
       by_status = {}
       recommendations = {}
       
       for classification in classifications:
           # Skip error classifications for summary
           if classification.get("error"):
               continue
           
           # Count by type
           doc_type = classification.get("document_type", "UNKNOWN")
           by_type[doc_type] = by_type.get(doc_type, 0) + 1
           
           # Count by importance
           importance = classification.get("importance", "UNKNOWN")
           by_importance[importance] = by_importance.get(importance, 0) + 1
           
           # Count by status
           status = classification.get("status", "UNKNOWN")
           by_status[status] = by_status.get(status, 0) + 1
           
           # Count by recommendation
           recommendation = classification.get("recommendation", "UNKNOWN")
           recommendations[recommendation] = recommendations.get(recommendation, 0) + 1
       
       return {
           "total_documents": len(classifications),
           "by_type": by_type,
           "by_importance": by_importance,
           "by_status": by_status,
           "recommendations": recommendations
       }
   
   def calculate_analysis_stats(
       self, 
       total_files: int,
       successful_classifications: List[Dict[str, Any]],
       failed_files: List[str],
       scan_time: float,
       estimated_cost: float
   ) -> Dict[str, Any]:
       """
       Calculate comprehensive analysis statistics
       
       Args:
           total_files: Total number of files processed
           successful_classifications: List of successful classifications
           failed_files: List of failed file names
           scan_time: Time taken for scanning in seconds
           estimated_cost: Estimated cost for the analysis
           
       Returns:
           Statistics dictionary
       """
       successful_count = len(successful_classifications)
       failed_count = len(failed_files)
       success_rate = (successful_count / total_files * 100) if total_files > 0 else 0
       
       # Count specific document types
       critical_docs = len([
           c for c in successful_classifications 
           if c.get("importance") == "CRITICAL"
       ])
       
       primary_contracts = len([
           c for c in successful_classifications 
           if c.get("document_type") == "PRIMARY_CONTRACT"
       ])
       
       executed_docs = len([
           c for c in successful_classifications 
           if c.get("status") == "EXECUTED_SIGNED"
       ])
       
       return {
           "total_documents": total_files,
           "successful_scans": successful_count,
           "failed_scans": failed_count,
           "success_rate": round(success_rate, 2),
           "critical_documents": critical_docs,
           "primary_contracts": primary_contracts,
           "executed_documents": executed_docs,
           "estimated_scan_cost": round(estimated_cost, 2),
           "scan_time_seconds": round(scan_time, 2)
       }


# Global instance
document_analyzer = DocumentAnalyzer()
