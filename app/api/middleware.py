from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
import time
import logging
from typing import Callable

from app.config import settings

logger = logging.getLogger("app.middleware")


async def logging_middleware(request: Request, call_next: Callable) -> Response:
   """Log request details and response time"""
   
   start_time = time.time()
   
   # Log request
   logger.info(
       f"Request: {request.method} {request.url.path}",
       extra={
           "method": request.method,
           "path": request.url.path,
           "query_params": str(request.query_params),
           "client_ip": request.client.host if request.client else None
       }
   )
   
   # Process request
   response = await call_next(request)
   
   # Calculate response time
   process_time = time.time() - start_time
   
   # Log response
   logger.info(
       f"Response: {response.status_code} - {process_time:.3f}s",
       extra={
           "status_code": response.status_code,
           "process_time": process_time,
           "path": request.url.path
       }
   )
   
   # Add timing header
   response.headers["X-Process-Time"] = str(process_time)
   
   return response


def setup_middleware(app: FastAPI) -> None:
   """Setup all middleware for the FastAPI application"""
   
   # CORS middleware
   app.add_middleware(
       CORSMiddleware,
       allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
       allow_credentials=True,
       allow_methods=["GET", "POST", "PUT", "DELETE"],
       allow_headers=["*"],
   )
   
   # Trusted host middleware (for production)
   if not settings.debug:
       app.add_middleware(
           TrustedHostMiddleware,
           allowed_hosts=["localhost", "127.0.0.1", settings.host]
       )
   
   # Custom logging middleware
   app.middleware("http")(logging_middleware)
   
   logger.info("Middleware configured")
