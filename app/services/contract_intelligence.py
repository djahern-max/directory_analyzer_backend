import logging
import time
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path
from datetime import datetime

from app.services.directory_scanner import directory_scanner
from app.services.pdf_extractor import pdf_extractor
from app.services.ai_classifier import create_ai_classifier
from app.services.document_analyzer import document_analyzer
from app.config import settings
from app.core.exceptions import (
   DirectoryAnalyzerException,
   PDFExtractionError,
   AIClassificationError
)

logger = logging.getLogger("app.services.contract_intelligence")


class ContractIntelligenceService:
   """
   Main service that orchestrates the complete directory analysis workflow
   """
   
   def __init__(self, api_key: str):
       self.api_key = api_key
       self.ai_classifier = create_ai_classifier(api_key)
       self.logger = logger
   
   def analyze_directory_complete(self, directory_path: str) -> Dict[str, Any]:
       """
       Complete directory analysis workflow
       
       Args:
           directory_path: Path to directory containing PDF files
           
       Returns:
           Complete analysis results including main contract identification
           
       Raises:
           DirectoryAnalyzerException: If analysis fails
       """
       start_time = time.time()
       
       try:
           self.logger.info(f"Starting complete directory analysis: {directory_path}")
           
           # Step 1: Scan directory for PDF files
           self.logger.info("Step 1: Scanning directory for PDF files")
           scan_result = directory_scanner.scan_directory(directory_path)
           
           job_name = scan_result["job_name"]
           job_number = scan_result["job_number"]
           pdf_files = [Path(file_info["file_path"]) for file_info in scan_result["files"]]
           
           self.logger.info(f"Found {len(pdf_files)} PDF files in job '{job_name}'")
           
           # Step 2: Process all PDF files
           self.logger.info("Step 2: Processing PDF files")
           classifications, failed_files = self._process_pdf_files(pdf_files, job_name)
           
           if not classifications:
               raise DirectoryAnalyzerException(
                   "No documents could be successfully processed",
                   details={
                       "total_files": len(pdf_files),
                       "failed_files": failed_files
                   }
               )
           
           # Step 3: Analyze and rank documents
           self.logger.info("Step 3: Analyzing and ranking documents")
           ranked_documents = document_analyzer.rank_documents(classifications)
           main_contract = document_analyzer.identify_main_contract(classifications)
           
           # Step 4: Generate analysis statistics
           scan_time = time.time() - start_time
           estimated_cost = len(pdf_files) * settings.estimated_cost_per_document
           
           stats = document_analyzer.calculate_analysis_stats(
               total_files=len(pdf_files),
               successful_classifications=classifications,
               failed_files=failed_files,
               scan_time=scan_time,
               estimated_cost=estimated_cost
           )
           
           classification_summary = document_analyzer.generate_classification_summary(classifications)
           
           # Step 5: Compile final results
           result = {
               "success": True,
               "message": self._generate_success_message(
                   len(classifications), len(pdf_files), main_contract
               ),
               "job_info": {
                   "job_name": job_name,
                   "job_number": job_number,
                   "directory_path": directory_path
               },
               "main_contract": main_contract,
               "ranked_documents": ranked_documents,
               "stats": stats,
               "classification_summary": classification_summary,
               "failed_files": failed_files,
               "timestamp": datetime.utcnow().isoformat()
           }
           
           self.logger.info(
               f"Directory analysis completed successfully in {scan_time:.1f}s. "
               f"Main contract: {main_contract['filename'] if main_contract else 'Not identified'}"
           )
           
           return result
           
       except Exception as e:
           scan_time = time.time() - start_time
           self.logger.error(f"Directory analysis failed after {scan_time:.1f}s: {e}")
           raise DirectoryAnalyzerException(
               f"Directory analysis failed: {str(e)}",
               details={
                   "directory_path": directory_path,
                   "scan_time_seconds": scan_time,
                   "error_type": type(e).__name__
               }
           )
   
   def identify_main_contract_only(self, directory_path: str) -> Dict[str, Any]:
       """
       Quick workflow to identify just the main contract
       
       Args:
           directory_path: Path to directory containing PDF files
           
       Returns:
           Main contract identification results
       """
       start_time = time.time()
       
       try:
           # Run the complete analysis
           full_result = self.analyze_directory_complete(directory_path)
           
           if full_result["success"] and full_result["main_contract"]:
               main_contract = full_result["main_contract"]
               scan_time = time.time() - start_time
               
               return {
                   "success": True,
                   "job_name": full_result["job_info"]["job_name"],
                   "job_number": full_result["job_info"]["job_number"],
                   "directory_path": directory_path,
                   "main_contract": {
                       "filename": main_contract["filename"],
                       "file_path": main_contract.get("file_path", ""),
                       "importance_score": main_contract.get("importance_score", 0),
                       "ranking_reason": main_contract.get("ranking_reason", ""),
                       "document_type": main_contract.get("document_type", "UNKNOWN"),
                       "summary": main_contract.get("summary", ""),
                       "confidence": main_contract.get("confidence", "MEDIUM")
                   },
                   "total_documents": full_result["stats"]["total_documents"],
                   "scan_time_seconds": scan_time,
                   "confidence": self._determine_identification_confidence(main_contract)
               }
           else:
               return {
                   "success": False,
                   "error": "Could not identify main contract",
                   "job_name": full_result.get("job_info", {}).get("job_name", "Unknown"),
                   "job_number": full_result.get("job_info", {}).get("job_number", "Unknown"),
                   "directory_path": directory_path,
                   "suggestion": "Review documents manually or check if directory contains contract files",
                   "total_documents": full_result.get("stats", {}).get("total_documents", 0),
                   "scan_time_seconds": time.time() - start_time
               }
               
       except Exception as e:
           scan_time = time.time() - start_time
           self.logger.error(f"Main contract identification failed: {e}")
           
           return {
               "success": False,
               "error": str(e),
               "job_name": "Unknown",
               "job_number": "Unknown", 
               "directory_path": directory_path,
               "suggestion": "Check directory path and ensure it contains PDF files",
               "scan_time_seconds": scan_time
           }
   
   def _process_pdf_files(
       self, 
       pdf_files: List[Path], 
       job_name: str
   ) -> Tuple[List[Dict[str, Any]], List[str]]:
       """
       Process all PDF files: extract text and classify
       
       Args:
           pdf_files: List of PDF file paths
           job_name: Name of the job for context
           
       Returns:
           Tuple of (successful_classifications, failed_files)
       """
       classifications = []
       failed_files = []
       
       for i, pdf_file in enumerate(pdf_files, 1):
           self.logger.info(f"Processing {i}/{len(pdf_files)}: {pdf_file.name}")
           
           try:
               # Extract text from PDF
               self.logger.debug(f"Extracting text from {pdf_file.name}")
               document_text = pdf_extractor.extract_text_from_file(pdf_file)
               
               if not document_text or len(document_text.strip()) < 50:
                   raise PDFExtractionError(
                       f"Insufficient text extracted from {pdf_file.name}",
                       details={"text_length": len(document_text) if document_text else 0}
                   )
               
               # Classify document
               self.logger.debug(f"Classifying {pdf_file.name}")
               classification = self.ai_classifier.classify_document(
                   document_text, pdf_file.name, job_name
               )
               
               # Add file metadata
               file_stats = pdf_file.stat()
               classification.update({
                   "file_path": str(pdf_file),
                   "file_size_kb": file_stats.st_size // 1024,
                   "text_length": len(document_text),
               })
               
               classifications.append(classification)
               
               self.logger.info(
                   f"Successfully processed {pdf_file.name} -> "
                   f"{classification.get('document_type', 'UNKNOWN')}"
               )
               
           except (PDFExtractionError, AIClassificationError) as e:
               error_msg = f"{pdf_file.name}: {str(e)}"
               failed_files.append(error_msg)
               self.logger.warning(f"Failed to process {pdf_file.name}: {e}")
               
           except Exception as e:
               error_msg = f"{pdf_file.name}: Unexpected error - {str(e)}"
               failed_files.append(error_msg)
               self.logger.error(f"Unexpected error processing {pdf_file.name}: {e}")
       
       self.logger.info(
           f"Processing complete: {len(classifications)} successful, "
           f"{len(failed_files)} failed"
       )
       
       return classifications, failed_files
   
   def _generate_success_message(
       self, 
       successful_count: int, 
       total_count: int, 
       main_contract: Optional[Dict[str, Any]]
   ) -> str:
       """Generate a descriptive success message"""
       
       main_contract_info = ""
       if main_contract:
           main_contract_info = f" Main contract: {main_contract['filename']}"
       else:
           main_contract_info = " Main contract: Not identified"
       
       return (
           f"Successfully analyzed {successful_count} of {total_count} documents."
           f"{main_contract_info}"
       )
   
   def _determine_identification_confidence(
       self, 
       main_contract: Optional[Dict[str, Any]]
   ) -> str:
       """Determine confidence level for main contract identification"""
       
       if not main_contract:
           return "LOW"
       
       score = main_contract.get("importance_score", 0)
       doc_type = main_contract.get("document_type", "")
       ai_confidence = main_contract.get("confidence", "MEDIUM")
       
       # High confidence criteria
       if (score > 120 and 
           doc_type == "PRIMARY_CONTRACT" and 
           ai_confidence == "HIGH"):
           return "HIGH"
       
       # Medium confidence criteria  
       elif (score > 80 and 
             doc_type == "PRIMARY_CONTRACT"):
           return "MEDIUM"
       
       # Otherwise low confidence
       else:
           return "LOW"
   
   def get_service_status(self) -> Dict[str, Any]:
       """Get status of the contract intelligence service"""
       
       return {
           "service": "ContractIntelligenceService",
           "status": "operational",
           "ai_model": settings.anthropic_model,
           "max_retries": settings.anthropic_max_retries,
           "timeout": settings.anthropic_timeout,
           "estimated_cost_per_document": settings.estimated_cost_per_document,
           "components": {
               "directory_scanner": "operational",
               "pdf_extractor": "operational",
               "ai_classifier": "operational", 
               "document_analyzer": "operational"
           }
       }


def create_contract_intelligence_service(api_key: str) -> ContractIntelligenceService:
   """Factory function to create a contract intelligence service"""
   return ContractIntelligenceService(api_key)
