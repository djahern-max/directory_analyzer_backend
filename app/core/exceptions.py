from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
import logging
from typing import Any, Dict

logger = logging.getLogger("app.exceptions")


class DirectoryAnalyzerException(Exception):
   """Base exception for Directory Analyzer application"""
   
   def __init__(self, message: str, details: Dict[str, Any] = None):
       self.message = message
       self.details = details or {}
       super().__init__(self.message)


class DirectoryNotFoundError(DirectoryAnalyzerException):
   """Raised when a directory cannot be found or accessed"""
   pass


class DirectoryEmptyError(DirectoryAnalyzerException):
   """Raised when a directory contains no PDF files"""
   pass


class PDFExtractionError(DirectoryAnalyzerException):
   """Raised when PDF text extraction fails"""
   pass


class AIClassificationError(DirectoryAnalyzerException):
   """Raised when AI classification fails"""
   pass


class InvalidDirectoryPathError(DirectoryAnalyzerException):
   """Raised when directory path is invalid"""
   pass


async def directory_analyzer_exception_handler(
   request: Request, exc: DirectoryAnalyzerException
) -> JSONResponse:
   """Handle custom DirectoryAnalyzer exceptions"""
   
   logger.error(f"Application error: {exc.message}", extra={"details": exc.details})
   
   return JSONResponse(
       status_code=400,
       content={
           "error": "DirectoryAnalyzerError",
           "message": exc.message,
           "details": exc.details
       }
   )


async def validation_exception_handler(
   request: Request, exc: RequestValidationError
) -> JSONResponse:
   """Handle request validation errors"""
   
   logger.warning(f"Validation error: {exc.errors()}")
   
   return JSONResponse(
       status_code=422,
       content={
           "error": "ValidationError",
           "message": "Request validation failed",
           "details": exc.errors()
       }
   )


async def http_exception_handler(
   request: Request, exc: StarletteHTTPException
) -> JSONResponse:
   """Handle HTTP exceptions"""
   
   logger.warning(f"HTTP error {exc.status_code}: {exc.detail}")
   
   return JSONResponse(
       status_code=exc.status_code,
       content={
           "error": "HTTPError",
           "message": exc.detail,
           "status_code": exc.status_code
       }
   )


async def general_exception_handler(request: Request, exc: Exception) -> JSONResponse:
   """Handle unexpected exceptions"""
   
   logger.error(f"Unexpected error: {str(exc)}", exc_info=True)
   
   return JSONResponse(
       status_code=500,
       content={
           "error": "InternalServerError",
           "message": "An unexpected error occurred",
           "details": str(exc) if logger.isEnabledFor(logging.DEBUG) else None
       }
   )


def setup_exception_handlers(app: FastAPI) -> None:
   """Setup exception handlers for the FastAPI application"""
   
   app.add_exception_handler(
       DirectoryAnalyzerException, 
       directory_analyzer_exception_handler
   )
   app.add_exception_handler(
       RequestValidationError, 
       validation_exception_handler
   )
   app.add_exception_handler(
       StarletteHTTPException, 
       http_exception_handler
   )
   app.add_exception_handler(
       Exception, 
       general_exception_handler
   )
   
   logger.info("Exception handlers configured")
