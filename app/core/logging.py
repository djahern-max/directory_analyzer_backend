import logging
import sys
from typing import Optional

from app.config import settings


def setup_logging(log_level: Optional[str] = None) -> None:
   """Setup application logging configuration"""
   
   level = log_level or settings.log_level
   
   # Configure root logger
   logging.basicConfig(
       level=getattr(logging, level.upper()),
       format=settings.log_format,
       handlers=[
           logging.StreamHandler(sys.stdout)
       ]
   )
   
   # Configure specific loggers
   
   # Reduce noise from external libraries
   logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
   logging.getLogger("httpx").setLevel(logging.WARNING)
   logging.getLogger("requests").setLevel(logging.WARNING)
   
   # Application logger
   app_logger = logging.getLogger("app")
   app_logger.setLevel(getattr(logging, level.upper()))
   
   logger = logging.getLogger(__name__)
   logger.info(f"Logging configured with level: {level}")


def get_logger(name: str) -> logging.Logger:
   """Get a logger instance for the given name"""
   return logging.getLogger(f"app.{name}")
