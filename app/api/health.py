from fastapi import APIRouter, Depends, HTTPException
from datetime import datetime
import logging
from typing import Dict, Any

from app.config import settings
from app.api.deps import get_api_key

router = APIRouter()
logger = logging.getLogger("app.health")


@router.get("/health")
async def health_check() -> Dict[str, Any]:
   """Basic health check endpoint"""
   
   return {
       "status": "healthy",
       "timestamp": datetime.utcnow().isoformat(),
       "service": settings.app_name,
       "version": "1.0.0"
   }


@router.get("/health/detailed")
async def detailed_health_check(api_key: str = Depends(get_api_key)) -> Dict[str, Any]:
   """Detailed health check including dependencies"""
   
   health_status = {
       "status": "healthy",
       "timestamp": datetime.utcnow().isoformat(),
       "service": settings.app_name,
       "version": "1.0.0",
       "environment": {
           "debug": settings.debug,
           "log_level": settings.log_level,
       },
       "dependencies": {}
   }
   
   # Check Anthropic API key configuration
   anthropic_status = "configured" if api_key else "missing"
   health_status["dependencies"]["anthropic_api"] = {
       "status": anthropic_status,
       "model": settings.anthropic_model
   }
   
   # Check if we can import required libraries
   try:
       import pdfplumber
       health_status["dependencies"]["pdfplumber"] = {"status": "available"}
   except ImportError:
       health_status["dependencies"]["pdfplumber"] = {"status": "missing"}
       health_status["status"] = "degraded"
   
   try:
       import requests
       health_status["dependencies"]["requests"] = {"status": "available"}
   except ImportError:
       health_status["dependencies"]["requests"] = {"status": "missing"}
       health_status["status"] = "degraded"
   
   # Overall status determination
   if any(
       dep.get("status") == "missing" 
       for dep in health_status["dependencies"].values()
   ):
       health_status["status"] = "unhealthy"
   
   logger.info(f"Health check completed: {health_status['status']}")
   
   return health_status


@router.get("/health/readiness")
async def readiness_check(api_key: str = Depends(get_api_key)) -> Dict[str, Any]:
   """Readiness check - determines if service is ready to handle requests"""
   
   try:
       # Test critical dependencies
       import pdfplumber
       import requests
       
       # Verify API key is configured
       if not api_key or api_key == "your_actual_anthropic_api_key_here":
           raise HTTPException(
               status_code=503,
               detail="Anthropic API key not properly configured"
           )
       
       return {
           "status": "ready",
           "timestamp": datetime.utcnow().isoformat(),
           "message": "Service is ready to handle requests"
       }
       
   except ImportError as e:
       logger.error(f"Missing required dependency: {e}")
       raise HTTPException(
           status_code=503,
           detail=f"Missing required dependency: {str(e)}"
       )
   except Exception as e:
       logger.error(f"Readiness check failed: {e}")
       raise HTTPException(
           status_code=503,
           detail=f"Service not ready: {str(e)}"
       )


@router.get("/health/liveness")
async def liveness_check() -> Dict[str, Any]:
   """Liveness check - determines if service is alive"""
   
   return {
       "status": "alive",
       "timestamp": datetime.utcnow().isoformat(),
       "message": "Service is alive"
   }
